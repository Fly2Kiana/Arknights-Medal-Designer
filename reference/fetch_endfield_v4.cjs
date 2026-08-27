// v4：B站搜索视频封面批量 + note.com 文章图
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 2) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) {
      console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`);
      await sleep(800 * t);
    }
  }
  return null;
}
function dl(u, p, referer) {
  const h = Object.assign({}, UA);
  if (referer) h['Referer'] = referer;
  return retry(async () => {
    const r = await fetch(u, { headers: h });
    if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { cause: { code: r.status } });
    fs.writeFileSync(p, Buffer.from(await r.arrayBuffer()));
    console.log('saved', path.basename(p), fs.statSync(p).size);
    return true;
  }, path.basename(p), 2);
}
(async () => {
  const dir = path.join(__dirname, 'endfield2');
  fs.mkdirSync(dir, { recursive: true });

  // A. B站搜索：终末地 蚀刻章 相关视频封面
  console.log('== A. bili search covers ==');
  const kw = encodeURIComponent('终末地 蚀刻章');
  const sj = await retry(() => fetch(
    `https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=${kw}&page=1`,
    { headers: Object.assign({}, UA, { Referer: 'https://www.bilibili.com/' }) }).then(r => r.json()),
    'search');
  let vi = 0;
  if (sj && sj.data && sj.data.result) {
    for (const v of sj.data.result.slice(0, 12)) {
      vi++;
      const pic = (v.pic || '').replace(/^http:/, 'https:');
      if (!pic) continue;
      await dl(pic.startsWith('//') ? 'https:' + pic : pic,
        path.join(dir, 'cover_' + String(vi).padStart(2, '0') + '.jpg'), 'https://www.bilibili.com/');
      fs.appendFileSync(path.join(dir, '_covers.txt'), `${vi}\t${v.title.replace(/<[^>]+>/g, '')}\t${v.bvid}\n`);
    }
  } else console.log('search no result (maybe need cookie)');

  // B. note.com 勲章加工文章配图
  console.log('== B. note.com images ==');
  const nj = await retry(() => fetch('https://note.com/djent1080/n/nac432f1b2ca4',
    { headers: UA }).then(r => r.text()), 'note');
  if (nj) {
    const urls = [...new Set((nj.match(/https:\/\/assets\.st-note\.com[^"'\s)]+\.(?:png|jpg|jpeg)/g) || []))]
      .filter(u => !/\/ic_|\d+x\d+c/.test(u) === true || true).slice(0, 14);
    console.log('note imgs:', urls.length);
    let ni = 0;
    for (let i = 0; i < urls.length; i++) {
      ni++;
      await dl(urls[i].replace(/\\\//g, '/'), path.join(dir, 'note_' + String(ni).padStart(2, '0') + '.jpg'), 'https://note.com/');
    }
  }
})();
