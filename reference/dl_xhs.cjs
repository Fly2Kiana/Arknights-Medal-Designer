// 下载小红书笔记模板图
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, 'xhs_note.html'), 'utf8');
const re = /urlDefault":"([^"]+)"/g;
const urls = [];
let m;
while ((m = re.exec(html)) !== null) {
  urls.push(m[1].replace(/\\u002F/g, '/').replace(/^http:/, 'https:'));
}
console.log('total urls:', urls.length);
const dir = path.join(__dirname, 'xhs');
fs.mkdirSync(dir, { recursive: true });
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36', 'Referer': 'https://www.xiaohongshu.com/' };
(async () => {
  for (let i = 0; i < urls.length; i++) {
    try {
      const r = await fetch(urls[i], { headers: UA });
      if (!r.ok) { console.log(i + 1, 'HTTP', r.status); continue; }
      const buf = Buffer.from(await r.arrayBuffer());
      if (buf.length < 3000) { console.log(i + 1, 'too small', buf.length); continue; }
      fs.writeFileSync(path.join(dir, 'xhs_' + (i + 1) + '.jpg'), buf);
      console.log(i + 1, 'saved', buf.length);
    } catch (e) { console.log(i + 1, 'ERR', e.message); }
  }
})();
