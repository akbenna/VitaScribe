// Foto in het dossier: welk uploadveld van de pagina de foto krijgt.
const test = require('node:test');
const assert = require('node:assert');
const F = require('../../chrome-extension/content/foto-upload.js');

test('neemtAfbeelding: wat een foto mag ontvangen', () => {
  ['', 'image/*', '.jpg,.png', 'image/jpeg', '*/*', 'application/pdf, image/png'].forEach((a) => assert.ok(F.neemtAfbeelding(a), a));
  ['application/pdf', '.docx', 'video/*'].forEach((a) => assert.ok(!F.neemtAfbeelding(a), a));
});

test('kies: het veld in het open venster, anders zichtbaar, anders het laatste', () => {
  const verborgen = { disabled: false, accept: '', zichtbaar: false, inDialoog: false };
  const zichtbaar = { disabled: false, accept: 'image/*', zichtbaar: true, inDialoog: false };
  const dialoog = { disabled: false, accept: '', zichtbaar: false, inDialoog: true };
  assert.strictEqual(F.kies([verborgen, zichtbaar]), 1);
  assert.strictEqual(F.kies([dialoog, zichtbaar]), 0);
  assert.strictEqual(F.kies([verborgen, verborgen]), 1);                       // the last one: newest dialog
  assert.strictEqual(F.kies([{ disabled: true, accept: '' }, { accept: 'application/pdf' }]), -1);
  assert.strictEqual(F.kies([]), -1);
});
