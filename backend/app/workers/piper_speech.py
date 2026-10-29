# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone Piper/ONNX speech adapter, distributed under GPLv3 or later.

Piper engine: https://github.com/OHF-Voice/piper1-gpl
License: https://www.gnu.org/licenses/gpl-3.0.html
This separate subprocess uses installed, unmodified Piper and ONNX Runtime.
The parent application supplies bounded UTF-8 text and receives a WAV file.
No resources are fetched and GPU providers are never enabled.
"""

import argparse
import json
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import onnxruntime
    from piper.config import PiperConfig
    from piper.voice import PiperVoice

    model = Path(args.model)
    source = Path(args.input)
    config_path = model.with_suffix(model.suffix + ".json")
    if (
        not model.is_file()
        or model.stat().st_size > 200_000_000
        or source.stat().st_size > 16_000
        or config_path.stat().st_size > 100_000
    ):
        raise ValueError("Speech input exceeds budget")
    text = source.read_text(encoding="utf-8")
    if not text.strip() or len(text) > 4000:
        raise ValueError("Speech text exceeds budget")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("phoneme_type") != "espeak" or not str(
        config.get("espeak", {}).get("voice", "")
    ).startswith("en"):
        raise ValueError("An installed English espeak voice is required")
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    voice = PiperVoice(
        session=onnxruntime.InferenceSession(
            str(model), sess_options=options, providers=["CPUExecutionProvider"]
        ),
        config=PiperConfig.from_dict(config),
    )
    with wave.open(args.output, "wb") as output:
        voice.synthesize_wav(text, output)


if __name__ == "__main__":
    main()
