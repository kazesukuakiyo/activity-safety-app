/* 名簿 (学籍番号・氏名・所属・学年) の貼り付けテキストを画面側で即時検証する。
 * サーバー側 (app/services/roster.py) と同じ規則。最終判定はサーバーで行う。 */
window.RosterParse = (function () {
  function parse(text) {
    const rows = [], errors = [], seen = new Set();
    text.split(/\r?\n/).forEach((raw, i) => {
      const line = raw.trim();
      if (!line) return;
      const cols = line.split(/\t|,|、|，/).map(c => c.trim());
      while (cols.length && cols[cols.length - 1] === '') cols.pop();
      if (cols.slice(0, 4).join() === '学籍番号,氏名,所属,学年') return;  // 見出し行
      if (cols.length !== 4) { errors.push((i + 1) + ' 行目: 列数が ' + cols.length + ' です (4 列にしてください)'); return; }
      if (cols.some(c => c === '')) { errors.push((i + 1) + ' 行目: 空欄があります'); return; }
      if (seen.has(cols[0])) { errors.push((i + 1) + ' 行目: 学籍番号 ' + cols[0] + ' が重複しています'); return; }
      seen.add(cols[0]);
      rows.push(cols);
    });
    return { rows, errors };
  }

  /* textarea の内容を解析して結果を表示する。戻り値は正常に読めた人数。
   * okMessage(rows) で成功時の文言を差し替えられる。 */
  function preview(textarea, out, okMessage) {
    if (!textarea.value.trim()) { out.hidden = true; return 0; }
    const { rows, errors } = parse(textarea.value);
    out.hidden = false;
    if (errors.length) {
      out.className = 'parse-result err';
      out.textContent = errors.join('\n');
      return 0;
    }
    out.className = 'parse-result ok';
    out.textContent = okMessage ? okMessage(rows) : rows.length + ' 名を読み取りました';
    return rows.length;
  }

  return { parse, preview };
})();
