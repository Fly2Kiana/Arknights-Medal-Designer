// 抓取小红书短链接：跳转 → 笔记页 → 提取标题/描述/图片
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 2) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) { console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`); await sleep(900 * t); }
  }
  return null;
}
(async () => {
  const short = 'https://xhslink.cn/o/4x64ViC9IGf';
  // 1. 跟踪重定向（manual redirect, 拿到最终 URL 与中间页）
  let r = await retry(() => fetch(short, { headers: UA, redirect: 'manual' }), 'shortlink');
  console.log('step1 status:', r && r.status, r && r.headers.get('location'));
  let url = r && r.headers.get('location') || short;
  let html = null;
  if (r && r.status === 302 && url.startsWith('http')) {
    html = await retry(() => fetch(url, { headers: UA, redirect: 'follow' }).then(x => x.text()), 'note page');
  }
  if (!html) {
    const r2 = await retry(() => fetch(short, { headers: UA, redirect: 'follow' }).then(x => x.text()), 'note follow');
    html = r2;
  }
  if (!html) { console.log('FETCH FAILED'); return; }
  fs.writeFileSync(path.join(__dirname, 'xhs_note.html'), html);
  console.log('html bytes:', html.length);
  const pick = (re) => (html.match(re) || [])[1] || null;
  console.log('title:', pick(/<meta name="og:title" content="([^"]+)"/) || pick(/<title>([^<]+)<\/title>/));
  console.log('desc :', (pick(/<meta name="og:description" content="([^"]+)"/) || '').slice(0, 300));
  const imgs = [...new Set(html.match(/https?:\\?\/\\?\/[^"'\s)]+?\.(?:jpg|jpeg|png|webp|heic)/gi) || [])]
    .map(u => u.replace(/\\\//g, '/')).filter(u => /xhscdn|sns-avatar|sns-img|ci\.xiaohongshu|xhslink|obj\.xiaohongshu/i.test(u));
  console.log('img candidates:', imgs.length);
  const dir = path.join(__dirname, 'xhs');
  fs.mkdirSync(dir, { recursive: true });
  let i = 0;
  for (const u of imgs.slice(0, 12)) {
    i++;
    const ok = await retry(async () => {
      const rr = await fetch(u, { headers: Object.assign({}, UA, { Referer: 'https://www.xiaohongshu.com/' }) });
      if (!rr.ok) throw Object.assign(new Error('HTTP ' + rr.status), { cause: { code: rr.status } });
      const buf = Buffer.from(await rr.arrayBuffer());
      if (buf.length > 3000) {
        const ext = (u.match(/\.(\w+)$/) || [,'jpg'])[1].toLowerCase();
        fs.writeFileSync(path.join(dir, `xhs_${String(i).padStart(2, '0')}.${ext}`), buf);
        console.log('saved xhs_' + i, buf.length);
      } else console.log('too small', u.slice(0, 80));
      return true;
    }, 'img' + i);
  }
})();
