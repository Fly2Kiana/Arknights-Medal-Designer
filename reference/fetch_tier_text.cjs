// 终末地品阶文本：note.com 文章 + game8 重试
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 3) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) { console.log(`  retry${t} ${tag}: ${e.message}`); await sleep(1200 * t); }
  }
  return null;
}
(async () => {
  const dir = __dirname;
  const strip = h => h.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<[^>]+>/g, '\n').replace(/&nbsp;/g, ' ').split('\n').map(s => s.trim()).filter(s => s.length > 2);

  // note.com 勲章加工
  console.log('== note.com text ==');
  const nj = await retry(() => fetch('https://note.com/djent1080/n/nac432f1b2ca4', { headers: UA }).then(r => r.text()), 'note');
  if (nj) {
    const lines = strip(nj).filter(s => /勲章|加工|銀|金|メッキ|極秘|レア|一覧|入手/.test(s)).slice(0, 60);
    fs.writeFileSync(path.join(dir, 'note_medal_text.txt'), lines.join('\n'));
    console.log(lines.join('\n').slice(0, 1800));
  }

  // game8 再试
  console.log('== game8 text ==');
  const g8 = await retry(() => fetch('https://game8.jp/arknights-endfield/763938', { headers: UA }).then(r => r.text()), 'game8');
  if (g8) {
    const lines = strip(g8).filter(s => /勲章|銀|金|メッキ|加工|極秘|レア/.test(s)).slice(0, 60);
    fs.writeFileSync(path.join(dir, 'game8_medal_text.txt'), lines.join('\n'));
    console.log(lines.join('\n').slice(0, 1800));
  }
})();
