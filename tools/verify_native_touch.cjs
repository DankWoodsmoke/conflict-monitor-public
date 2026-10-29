/* Bounded actual touchscreen/CDP gesture probe. No screenshots, traces,
 * publisher text, provider URLs, storage snapshots or keys are persisted. */
const { chromium } = require('../frontend/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.CM_BASE_URL || 'http://127.0.0.1:5190';
const output = process.env.CM_TOUCH_OUTPUT || 'artifacts/native-touch-final';
const receipt = { started_at: new Date().toISOString(), scope: 'Chromium desktop touch emulation with actual touchscreen taps and native CDP gestures', checks: [], findings: [], incomplete: [], limitations: [
  'This is not a physical Android or iOS device.',
  'Native pan acceptance alone is not a measured viewport change; the probe requires a large real-position hemisphere-mask change.',
  'A successful touch interaction is not long-term GPU or provider reliability evidence.'
] };
if (fs.existsSync(output)) throw new Error('Preserve existing touch receipt; select a fresh output path');
fs.mkdirSync(output, { recursive: true });
const safe = value => String(value).replace(/https?:\/\/[^\s"<>]+/g, '[URL omitted]').replace(/([?&]key=)[^\s&]+/g, '$1[redacted]').slice(0, 500);
const save = () => fs.writeFileSync(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2));
async function tap(page, locator) {
  const chosen = locator.first(); await chosen.waitFor({ state: 'visible' });
  const box = await chosen.boundingBox(); assert(box && box.width > 0 && box.height > 0);
  await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
}
async function sameCanvas(page, handle) {
  assert(await page.evaluate(node => node === document.querySelector('.cesium-widget canvas'), handle), 'Earth canvas remounted');
}
async function height(page) {
  const text = await page.locator('.earth-navigation small').innerText();
  const match = text.match(/([\d.]+)\s*(Mm|km)/); assert(match, 'No actual camera height exposed');
  return Number(match[1]) * (match[2] === 'Mm' ? 1000000 : 1000);
}
async function stableHeight(page) {
  let prior = null, same = 0;
  for (let attempt = 0; attempt < 50; attempt++) {
    const current = await height(page);
    same = current === prior ? same + 1 : 0; prior = current;
    if (same >= 4) return current;
    await page.waitForTimeout(100);
  }
  throw new Error('Observed camera height did not settle before native gesture');
}
(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
    receipt.browser = { name: 'chromium', version: browser.version(), viewport: { width: 390, height: 844 }, hasTouch: true };
    const context = await browser.newContext({ viewport: receipt.browser.viewport, hasTouch: true, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on('pageerror', error => receipt.findings.push({ type: 'uncaught_runtime', error: safe(error.message) }));
    await page.addInitScript(() => localStorage.setItem('cm_seen_methods_v2', '1'));
    await page.goto(base + '/?view=earth', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => document.querySelector('.earth-workspace')?.getAttribute('data-earth-provider') === 'ready', null, { timeout: 45000 });
    assert((await page.locator('.cesium-widget-credits').innerText()).includes('Google'));
    const canvas = await page.locator('.cesium-widget canvas').elementHandle();
    const nav = page.locator('.mobile-bottom-nav');
    for (const name of ['Media', 'Brief', 'Earth']) {
      await tap(page, nav.getByRole('button', { name: new RegExp(name) }));
      if (name !== 'Earth') await page.locator('.workspace-panel').waitFor({ state: 'visible' });
      else await page.locator('.workspace-panel').waitFor({ state: 'hidden' });
      await sameCanvas(page, canvas);
    }
    receipt.checks.push('actual_touchscreen_taps_all_three_tabs_preserve_canvas');
    const beforeZoom = await stableHeight(page);
    await tap(page, page.getByRole('button', { name: 'Zoom in', exact: true }));
    await page.waitForFunction(before => {
      const text = document.querySelector('.earth-navigation small')?.textContent || '';
      const m = text.match(/([\d.]+)\s*(Mm|km)/); return m && Number(m[1]) * (m[2] === 'Mm' ? 1e6 : 1e3) < before;
    }, beforeZoom, { timeout: 8000 });
    receipt.camera_tap_zoom = { before_meters: beforeZoom, after_meters: await height(page) };
    receipt.checks.push('touch_camera_zoom_changes_observed_height');
    await tap(page, page.getByRole('button', { name: /^Layers/ }));
    await page.locator('.earth-layer-panel').waitFor({ state: 'visible' });
    const aging = page.getByRole('checkbox', { name: 'Show last-known positions', exact: true });
    const prior = await aging.isChecked(); await tap(page, aging); assert.equal(await aging.isChecked(), !prior);
    await tap(page, aging); assert.equal(await aging.isChecked(), prior);
    await tap(page, page.getByRole('button', { name: /Close spatial layers/ }));
    receipt.checks.push('touch_layers_and_last_known_toggle');
    await tap(page, page.getByRole('button', { name: 'Settings', exact: true }));
    const dialog = page.getByRole('dialog'); await dialog.waitFor({ state: 'visible' });
    const close = dialog.getByRole('button', { name: /close/i });
    await tap(page, close); await dialog.waitFor({ state: 'hidden' });
    receipt.checks.push('touch_settings_open_and_close');
    const cdp = await context.newCDPSession(page);
    const canvasBox = await page.locator('.cesium-widget canvas').boundingBox(); assert(canvasBox);
    const x = canvasBox.x + canvasBox.width * .5;
    const y = canvasBox.y + canvasBox.height * .72;
    const beforePinch = await stableHeight(page);
    try {
      await cdp.send('Input.synthesizePinchGesture', { x, y, scaleFactor: 1.8, relativeSpeed: 450, gestureSourceType: 'touch' });
      await page.waitForFunction(before => {
        const m = (document.querySelector('.earth-navigation small')?.textContent || '').match(/([\d.]+)\s*(Mm|km)/);
        return m && Math.abs(Number(m[1]) * (m[2] === 'Mm' ? 1e6 : 1e3) - before) > Math.max(1000, before * .03);
      }, beforePinch, { timeout: 10000 });
      receipt.native_pinch = { accepted: true, before_meters: beforePinch, after_meters: await height(page) };
      receipt.checks.push('native_touch_pinch_changes_observed_camera_height');
    } catch (error) { receipt.incomplete.push({ type: 'native_pinch', error: safe(error.message) }); }
    try {
      await tap(page, page.getByRole('button', { name: 'Globe', exact: true }));
      await page.waitForFunction(() => /1[5-9]\.\d Mm|2\d\.\d Mm/.test(document.querySelector('.earth-navigation small')?.textContent || ''), null, { timeout: 8000 });
      await stableHeight(page);
      const counts = () => page.locator('.earth-coverage').evaluate(node => ({
        enabled: Number(node.getAttribute('data-position-count')), visible: Number(node.getAttribute('data-visible-count')) }));
      const beforePan = await counts(); let afterPan = beforePan;
      let measured = false;
      for (let attempt = 0; attempt < 3; attempt++) {
        await cdp.send('Input.synthesizeScrollGesture', { x: canvasBox.x + canvasBox.width / 2,
          y: canvasBox.y + canvasBox.height / 2, xDistance: 180, yDistance: 0, speed: 220, gestureSourceType: 'touch' });
        await page.waitForTimeout(700); afterPan = await counts();
        if (beforePan.visible >= 4 && afterPan.enabled === beforePan.enabled && afterPan.visible <= Math.floor(beforePan.visible / 4)) { measured = true; break; }
      }
      receipt.native_pan = { command_accepted: true, before: beforePan, after: afterPan,
        large_hemisphere_mask_change_measured: measured, exact_camera_center_measured: false };
      if (measured) receipt.checks.push('native_touch_pan_changes_actual_position_hemisphere_viewport');
      else receipt.incomplete.push({ type: 'native_pan_outcome', reason: 'Native commands accepted, but a sufficiently large viewport-mask change with unchanged position count was not observed.' });
    } catch (error) { receipt.incomplete.push({ type: 'native_pan_runtime', error: safe(error.message) }); }
    await tap(page, page.getByRole('button', { name: 'Region', exact: true }));
    await page.waitForFunction(() => Number(document.querySelector('.earth-coverage')?.getAttribute('data-visible-count')) > 0, null, { timeout: 10000 });
    await sameCanvas(page, canvas); receipt.checks.push('touch_region_restores_visible_hemisphere');
    await tap(page, page.locator('.feed-fab'));
    await page.locator('.feed-sheet').waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('.feed-sheet')?.getAnimations().every(animation => animation.playState === 'finished'), null, { timeout: 5000 });
    const candidates = await page.locator('.feed-sheet').evaluate(sheet => [...sheet.querySelectorAll('*')].filter(node => {
      const style = getComputedStyle(node); return /auto|scroll/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 30;
    }).map(node => ({ className: node.className, scrollTop: node.scrollTop, scrollHeight: node.scrollHeight, clientHeight: node.clientHeight })));
    assert(candidates.length, 'No actual scrollable report list');
    const box = await page.locator('.feed-sheet-body').boundingBox(); assert(box);
    const beforeScroll = await page.locator('.feed-sheet').evaluate(sheet => Math.max(...[...sheet.querySelectorAll('*')].map(node => Number(node.scrollTop) || 0), 0));
    // The Windows Chromium runtime accepted synthesizeScrollGesture but failed
    // to scroll even a native fixture. Dispatch real touch points instead of
    // substituting a mouse wheel or changing DOM scrollTop.
    const touchX = box.x + box.width * .65, touchY = box.y + box.height * .8;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: touchX, y: touchY }] });
    for (let step = 1; step <= 12; step++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: touchX, y: touchY - step * 15 }] });
      await page.waitForTimeout(16);
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForFunction(before => Math.max(...[...document.querySelectorAll('.feed-sheet *')].map(node => Number(node.scrollTop) || 0), 0) > before + 20, beforeScroll, { timeout: 6000 });
    receipt.feed_scroll = { method: 'Input.dispatchTouchEvent', before: beforeScroll, after: await page.locator('.feed-sheet').evaluate(sheet => Math.max(...[...sheet.querySelectorAll('*')].map(node => Number(node.scrollTop) || 0), 0)) };
    receipt.checks.push('native_touch_scroll_moves_report_list');
    await page.setViewportSize({ width: 844, height: 390 });
    await page.locator('.feed-sheet').waitFor({ state: 'hidden' });
    await sameCanvas(page, canvas);
    const layout = await page.evaluate(() => ({ width: innerWidth, scroll_width: document.documentElement.scrollWidth }));
    assert(layout.scroll_width <= layout.width + 1); receipt.landscape_layout = layout;
    receipt.checks.push('portrait_to_landscape_preserves_canvas_and_fits_viewport');
    await context.close();
  } catch (error) { receipt.findings.push({ type: 'probe_failure', error: safe(error.message) }); }
  finally { if (browser) await browser.close(); }
  receipt.ended_at = new Date().toISOString();
  receipt.status = receipt.findings.length ? 'FAIL' : receipt.incomplete.length ? 'PARTIAL/INCOMPLETE' : 'PASS';
  save(); console.log(JSON.stringify({ status: receipt.status, checks: receipt.checks.length, findings: receipt.findings, incomplete: receipt.incomplete }));
  process.exitCode = receipt.status === 'PASS' ? 0 : 1;
})().catch(error => { receipt.status = 'OBSERVER_FAILED'; receipt.findings.push({ error: safe(error.message) }); save(); process.exitCode = 1; });
