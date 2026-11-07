"""Offline exact-byte and config qualification; no tunnel, credentials or network."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import ssl
import struct
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL="cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba"


def docker(*args,timeout=40):
    result=subprocess.run(["docker",*args],capture_output=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError("Offline connector qualification failed: "+result.stderr.decode("utf8",errors="replace")[:1000])
    return result.stdout.decode("utf8")


def image_files(image,archive):
    docker("image","save","--output",str(archive),image,timeout=90)
    result={}
    with tarfile.open(archive) as saved:
        manifest=json.load(saved.extractfile("manifest.json"))[0]
        for name in manifest["Layers"]:
            with tarfile.open(fileobj=saved.extractfile(name),mode="r|*") as layer:
                for member in layer:
                    path=member.name.lstrip("./")
                    if member.isfile():
                        if member.size>64*1024**2:
                            raise ValueError("Unexpected image file size")
                        result[path]=layer.extractfile(member).read()
    return result


def qualify(image):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}",image):
        raise ValueError("Supply the exact locally built connector image ID")
    provenance=json.loads((ROOT/"tools/hosting/cloudflared-provenance.json").read_bytes())
    metadata=json.loads(docker("image","inspect",image))[0]
    checks={"local_identity_exact":metadata["Id"]==image,"nonroot_default":metadata["Config"]["User"]=="65532:65532"}
    env=dict(item.split("=",1) for item in metadata["Config"]["Env"])
    checks["autoupdate_disabled"]=env.get("NO_AUTOUPDATE")=="true"
    prefix="cm-connector-check-"+secrets.token_hex(6)
    commands={}
    with tempfile.TemporaryDirectory(prefix=prefix+"-") as temporary:
        base=Path(temporary)
        official=image_files(OFFICIAL,base/"official.tar")
        minimal=image_files(image,base/"minimal.tar")
        binary=minimal["usr/local/bin/cloudflared"]
        certs=minimal["etc/ssl/certs/ca-certificates.crt"]
        checks["official_binary_byte_identical"]=binary==official["usr/local/bin/cloudflared"] and hashlib.sha256(binary).hexdigest()==provenance["binary_sha256"]
        checks["official_ca_bundle_byte_identical"]=certs==official["etc/ssl/certs/ca-certificates.crt"] and hashlib.sha256(certs).hexdigest()==provenance["ca_bundle_sha256"]
        checks["official_identity_files_preserved"]=all(minimal[name]==official[name] for name in ["etc/passwd","etc/group"])
        checks["official_ca_license_and_metadata_preserved"]=minimal["usr/share/doc/ca-certificates/copyright"]==official["usr/share/doc/ca-certificates/copyright"] and minimal["opt/provenance/ca-certificates.package-metadata"]==official["var/lib/dpkg/status.d/ca-certificates"]
        checks["licenses_and_provenance_included"]=minimal["opt/licenses/cloudflared-THIRD_PARTY_LICENSES.txt"]==(ROOT/"tools/hosting/THIRD_PARTY_LICENSES.txt").read_bytes() and minimal["opt/provenance/cloudflared.json"]==(ROOT/"tools/hosting/cloudflared-provenance.json").read_bytes()
        checks["only_eight_intended_regular_files"]=set(minimal)=={"usr/local/bin/cloudflared","etc/ssl/certs/ca-certificates.crt","etc/passwd","etc/group","usr/share/doc/ca-certificates/copyright","opt/provenance/ca-certificates.package-metadata","opt/licenses/cloudflared-THIRD_PARTY_LICENSES.txt","opt/provenance/cloudflared.json"}
        if binary[:6]!=b"\x7fELF\x02\x01":raise ValueError("Expected little-endian ELF64")
        header=struct.unpack_from("<HHIQQQIHHHHHH",binary,16)
        types=[struct.unpack_from("<I",binary,header[4]+i*header[8])[0] for i in range(header[9])]
        checks["no_elf_interpreter_or_dynamic_linkage"]=not any(kind in [2,3] for kind in types)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=certs.decode("ascii"))
        checks["ca_bundle_parses_and_contains_roots"]=context.cert_store_stats()["x509_ca"]>100
        config=ROOT/"tools/hosting/cloudflared.example.yml"
        for key,args,expected in [
            ("version",["version"],"cloudflared version 2026.10.7"),
            ("help",["--help"],"cloudflared"),
            ("config_valid",["tunnel","--config","/fixture.yml","ingress","validate"],"OK"),
            ("hostname_route",["tunnel","--config","/fixture.yml","ingress","rule","https://monitor.ianmalcolm84.com/"],"http://publicfrontend:80"),
            ("unmatched_host_404",["tunnel","--config","/fixture.yml","ingress","rule","https://unmatched.invalid/"],"http_status:404"),
        ]:
            name=prefix+"-"+key
            try:
                command=["docker","run","--rm","--name",name,"--network=none","--read-only","--cap-drop=ALL",
                         "--security-opt=no-new-privileges:true","--memory=128m","--cpus=0.5","--pids-limit=32",
                         "--mount",f"type=bind,source={config},target=/fixture.yml,readonly",image,*args]
                result=subprocess.run(command,capture_output=True,timeout=20)
                output=(result.stdout+result.stderr).decode("utf8",errors="replace")
                checks["offline_"+key]=result.returncode==0 and expected in output
                commands[key]={"exit_code":result.returncode,"output_sha256":hashlib.sha256(output.encode()).hexdigest()}
            finally:
                if docker("ps","-aq","--filter","name="+name).strip():docker("rm","--force",name)
    checks["cleanup_verified"]=not docker("ps","-aq","--filter","name="+prefix).strip()
    return {"checked_at":datetime.now(UTC).isoformat(),"status":"PASS" if all(checks.values()) else "FAIL",
            "checks":checks,"image":image,"official_source":OFFICIAL,"binary_sha256":provenance["binary_sha256"],
            "ca_bundle_sha256":provenance["ca_bundle_sha256"],"ca_roots":context.cert_store_stats()["x509_ca"],
            "offline_commands":commands,"tool_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "network":"none","tunnel_started":False,"credentials_used":False,
            "limitations":["Offline CLI/config and byte-preservation checks do not prove actual tunnel establishment, TLS or public routing.",
                            "Fresh raw vulnerability and complete SBOM comparisons are separate retained receipts."]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=qualify(args.image)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)
