// Exercise the same on-demand tools and refinement controls used in the UI.
exports.view = async (page, id) => {
  const drawer = page.locator('#workspace-tools');
  if (await drawer.evaluate(node => node.open)) await page.locator('#workspace-tools-close').click();
  if (['plan', 'assets', 'report', 'activity', 'library'].includes(id)) {
    await page.locator('#workspace-tools-open').click();
    const section = page.locator('#tools-' + id);
    if (!await section.evaluate(node => node.open)) await section.locator(':scope > summary').click();
    await page.locator('#' + id).scrollIntoViewIfNeeded();
  } else if (id === 'playtest' || id === 'polish') {
    const section = page.locator('#playtest');
    if (!await section.evaluate(node => node.open)) await section.locator(':scope > summary').click();
  }
};
