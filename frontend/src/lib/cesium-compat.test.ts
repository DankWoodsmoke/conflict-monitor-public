import {afterEach,describe,expect,it,vi} from "vitest";
import {Color,Material} from "cesium";

afterEach(()=>vi.unstubAllGlobals());
describe("Cesium materials without OffscreenCanvas",()=>{
 it("constructs a genuine ColorMaterial while the unsupported browser global stays absent",()=>{
   // jsdom lacks ImageBitmap independently; this fixture leaves OffscreenCanvas absent.
   vi.stubGlobal("ImageBitmap",class ImageBitmapFixture{});vi.stubGlobal("OffscreenCanvas",undefined);
   expect(typeof globalThis.OffscreenCanvas).toBe("undefined");
   const material=Material.fromType("Color",{color:Color.RED});
   expect(material.uniforms.color).toEqual(Color.RED);expect(typeof globalThis.OffscreenCanvas).toBe("undefined");
 });
});
