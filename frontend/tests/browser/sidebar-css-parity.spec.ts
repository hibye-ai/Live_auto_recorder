import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { PNG } from 'pngjs';
import { mockConsoleApi } from './fixtures';

const candidate = readFileSync('../templates/static/css/console.css', 'utf8');
const anchor = '  body.lar-sidebar-collapsed .lar-sidebar-list { padding-top: 12px; align-items: center; }';
const removed = '  body.lar-sidebar-collapsed .sidenav { padding-left: 8px !important; padding-right: 8px !important; }\n';
const baseline = candidate.replace(anchor, removed + anchor);
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
test('only the earlier duplicate collapsed sidebar rule changes', () => {
  expect(baseline).not.toEqual(candidate);
  expect(baseline.replace(removed, '')).toBe(candidate);
});

for (const viewport of [{width:1440, height:1050}, {width:360, height:800}]) {
  for (const path of screens) {
    test(`collapsed sidebar CSS parity ${path} ${viewport.width}`, async ({page}, testInfo) => {
      await page.setViewportSize(viewport);
      await page.addInitScript(() => localStorage.setItem('lar-sidebar-collapsed', '1'));
      await page.clock.setFixedTime(new Date('2026-10-11T12:00:00Z'));
      await mockConsoleApi(page);
      await page.route('**/api/files/roots', route => route.fulfill({json: {roots:[{path:'/synthetic', label:'합성 경로'}], default:'/synthetic'}}));
      let css = baseline;
      await page.route('**/static/css/console.css*', route => route.fulfill({contentType:'text/css', body:css}));
      await page.goto(path);
      await page.addStyleTag({content: '*, *::before, *::after { animation: none !important; transition: none !important; } #ops-notice, .lar-toast-region { visibility: hidden !important; } html, * { scroll-behavior: auto !important; }'});
      await page.waitForTimeout(500);
      if (path !== '/register' && viewport.width > 1100) {
        await expect(page.locator('body')).toHaveClass(/lar-sidebar-collapsed/);
        await page.locator('.lar-sidebar-collapse').hover();
      }
      if (path !== '/register' && path !== '/files' && viewport.width < 1100) {
        await page.locator('.menu-icon').first().click();
      }
      await page.keyboard.press('Tab');
      await page.waitForTimeout(250);
      const before = await capture(page);
      css = candidate;
      await page.evaluate(() => {
        const sheet = Array.from(document.styleSheets).find(sheet => sheet.href?.includes('console.css'));
        if (sheet) {
          const groups = Array.from(sheet.cssRules).filter(rule => rule instanceof CSSMediaRule && rule.conditionText === '(min-width: 1100px)') as CSSMediaRule[];
          const group = groups.find(item => Array.from(item.cssRules).some(rule => rule instanceof CSSStyleRule && rule.selectorText === 'body.lar-sidebar-collapsed .sidenav'));
          if (!group) throw new Error('baseline collapsed sidebar rule not found');
          const index = Array.from(group.cssRules).findIndex(rule => rule instanceof CSSStyleRule && rule.selectorText === 'body.lar-sidebar-collapsed .sidenav');
          group.deleteRule(index);
        }
      });
      const after = await capture(page);
      expect(after.state).toEqual(before.state);
      await testInfo.attach('baseline', {body: before.image, contentType: 'image/png'});
      await testInfo.attach('candidate', {body: after.image, contentType: 'image/png'});
      const beforePixels = PNG.sync.read(before.image);
      const afterPixels = PNG.sync.read(after.image);
      expect([afterPixels.width, afterPixels.height]).toEqual([beforePixels.width, beforePixels.height]);
      // Chromium may vary anti-aliasing by one or two colour levels between frames.
      let changedChannels = 0;
      for (let i = 0; i < beforePixels.data.length; i++) {
        if (Math.abs(beforePixels.data[i] - afterPixels.data[i]) > 2) changedChannels++;
      }
      expect(changedChannels).toBe(0);
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
