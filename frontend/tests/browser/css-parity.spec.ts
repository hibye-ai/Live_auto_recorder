import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { mockConsoleApi } from './fixtures';

const candidate = readFileSync('../templates/static/css/console.css', 'utf8');
const baseline = candidate.replace('*::before, *::after { box-sizing: border-box; }', '*, *::before, *::after { box-sizing: border-box; }');
const screens = ['/', '/recording', '/channels', '/config', '/cookies', '/files', '/operations', '/register'];

async function capture(page: Page) {
  await page.evaluate(async () => { await document.fonts.ready; });
  const state = await page.evaluate(() => ({
    focus: document.activeElement?.outerHTML,
    styles: Array.from(document.querySelectorAll('html, body, body *')).map(element => {
      const style = getComputedStyle(element);
      return [element.tagName, element.id, style.boxSizing,
        getComputedStyle(element, '::before').boxSizing,
        getComputedStyle(element, '::after').boxSizing,
        style.fontFamily, style.fontSize, style.outlineStyle, style.outlineWidth];
    }),
  }));
  return { state, image: await page.screenshot({fullPage: true, animations: 'disabled', caret: 'hide'}) };
}
test('only the redundant universal declaration changes', () => {
  expect(baseline).not.toEqual(candidate);
  expect(baseline.replace('*, *::before, *::after { box-sizing: border-box; }', '*::before, *::after { box-sizing: border-box; }')).toBe(candidate);
});

for (const viewport of [{width:1440, height:1050}, {width:360, height:800}]) {
  for (const path of screens) {
    test(`legacy CSS parity ${path} ${viewport.width}`, async ({page}, testInfo) => {
      await page.setViewportSize(viewport);
      await mockConsoleApi(page);
      let css = baseline;
      await page.route('**/static/css/console.css*', route => route.fulfill({contentType:'text/css', body:css}));
      await page.goto(path);
      await page.addStyleTag({content: '*, *::before, *::after { animation: none !important; transition: none !important; } #ops-notice { visibility: hidden !important; }'});
      await page.waitForTimeout(500);
      await page.keyboard.press('Tab');
      const before = await capture(page);
      css = candidate;
      await page.evaluate(() => {
        const sheet = Array.from(document.styleSheets).find(sheet => sheet.href?.includes('console.css'));
        if (sheet) {
          const rule = Array.from(sheet.cssRules).find(rule => rule instanceof CSSStyleRule && rule.selectorText === '*, ::before, ::after') as CSSStyleRule | undefined;
          if (!rule) throw new Error('baseline box-sizing rule not found');
          rule.selectorText = '::before, ::after';
        }
      });
      const after = await capture(page);
      expect(after.state).toEqual(before.state);
      await testInfo.attach('baseline', {body: before.image, contentType: 'image/png'});
      await testInfo.attach('candidate', {body: after.image, contentType: 'image/png'});
      expect(after.image.equals(before.image)).toBe(true);
      if (path === '/recording') {
        await expect(page.locator('#start-all-recording')).toBeVisible();
        await expect(page.locator('#stop-all-recording')).toBeVisible();
        const toggle = page.locator('.toggle-record-enabled').first();
        await expect(toggle).toHaveCount(1);
        await toggle.focus();
        await expect(toggle).toBeFocused();
        expect(await toggle.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe('none');
        let toggled = false;
        await page.route('**/api/toggle_record_enabled/ch-1', async route => {
          toggled = route.request().method() === 'POST';
          await route.fulfill({json: {status:'success', channel_id:'ch-1', record_enabled:false}});
        });
        await page.keyboard.press('Space');
        await expect.poll(() => toggled).toBe(true);
        await expect(toggle).not.toBeChecked();
      }
      const fallback = await page.evaluate(async () => {
        const element = document.createElement('span');
        element.textContent = '한글 녹화 설정';
        element.style.fontFamily = '"missing-test-face", "Noto Sans CJK KR", sans-serif';
        element.id = 'fallback-font-probe';
        document.body.appendChild(element);
        await document.fonts.ready;
        return {width: element.getBoundingClientRect().width, family: getComputedStyle(element).fontFamily};
      });
      expect(fallback.width).toBeGreaterThan(0);
      expect(fallback.family).toContain('Noto Sans CJK KR');
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('DOM.enable');
      await cdp.send('CSS.enable');
      const documentNode = await cdp.send('DOM.getDocument');
      const probe = await cdp.send('DOM.querySelector', {nodeId: documentNode.root.nodeId, selector: '#fallback-font-probe'});
      const fonts = await cdp.send('CSS.getPlatformFontsForNode', {nodeId: probe.nodeId});
      expect(fonts.fonts.some(font => font.glyphCount > 0 && !font.familyName.includes('missing-test-face'))).toBe(true);
      await cdp.detach();
    });
  }
}
