// Collection parser v2. Decode saved public data only; never execute page scripts.
// Paste into the existing "Extract original post" Code node (all items mode).
const plain = text => typeof text === 'string' && text.trim().length > 0 && !/<\/?[A-Za-z][^>]*>/.test(text);
const idFromUrl = value => {
  if (typeof value !== 'string') return null;
  const match = /^https:\/\/support\.google\.com\/photos\/thread\/(\d+)(?:\/[^/?#]*)?\/?(?:\?[^#]*)?(?:#.*)?$/.exec(value);
  return match ? match[1] : null;
};
function decodeLiteral(encoded) {
  let result = '';
  const escapes = {n:'\n', r:'\r', t:'\t', b:'\b', f:'\f', '\\':'\\', "'":"'", '"':'"', '/':'/'};
  for (let i=0; i<encoded.length; i++) {
    if (encoded[i] !== '\\') { result += encoded[i]; continue; }
    const escape = encoded[++i];
    if (escape === 'x' || escape === 'u') {
      const width = escape === 'x' ? 2 : 4;
      const digits = encoded.slice(i+1, i+1+width);
      if (digits.length !== width || !/^[0-9a-f]+$/i.test(digits)) throw Error('unsupported literal');
      result += String.fromCharCode(parseInt(digits,16)); i += width;
    } else if (Object.prototype.hasOwnProperty.call(escapes,escape)) result += escapes[escape];
    else throw Error('unsupported literal');
  }
  return result;
}
const outputs = [];
for (let i=0; i<$input.all().length; i++) {
  const seed = $('Validate bounds').all()[i].json;
  const html = $input.all()[i].json.html;
  let question = null, path = 'QAPage.mainEntity.text', failure = 'no_verified_plain_original_post';
  const questions = [];
  const visit = value => {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) { value.forEach(visit); return; }
    if ([].concat(value['@type'] || []).includes('QAPage') && value.mainEntity && !Array.isArray(value.mainEntity)) questions.push(value.mainEntity);
    if (value['@graph']) visit(value['@graph']);
  };
  if (typeof html === 'string') {
    for (const match of html.matchAll(/<script\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script\s*>/gi)) {
      try { visit(JSON.parse(match[1])); } catch (_) { /* malformed structured data is refused */ }
    }
    if (questions.length === 1) {
      question = questions[0];
      if (question.url && idFromUrl(question.url) !== seed.source_item_id) {
        question = null; failure = 'thread_identity_mismatch';
      }
    } else if (questions.length > 1) failure = 'ambiguous_original_post';
    else {
      // Current public thread_view bootstrap: FU field 2 = thread, QJ field
      // 13 = body; QJ field 9 = title; info field 2 = created microseconds.
      // Field indices are verified against the retained page's renderer.
      const declarations = [];
      for (const script of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
        if (/\bsrc\s*=/i.test(script[1])) continue;
        for (const match of script[2].matchAll(/\bvar\s+thread_view\s*=\s*'((?:\\[\s\S]|[^'\\])*)'\s*;/g)) declarations.push(match[1]);
      }
      if (declarations.length > 1) failure = 'ambiguous_original_post';
      else if (declarations.length === 1) {
        failure = 'unsupported_thread_bootstrap';
        try {
          const view = JSON.parse(decodeLiteral(declarations[0]));
          const thread = Array.isArray(view) ? view[1] : null;
          const info = Array.isArray(thread) ? thread[0] : null;
          const author = Array.isArray(view) ? view[3] : null;
          const canonical = [];
          for (const link of html.matchAll(/<link\b([^>]*)>/gi)) {
            if (/\brel\s*=\s*["']canonical["']/i.test(link[1])) {
              const href = /\bhref\s*=\s*["']([^"']+)["']/i.exec(link[1]);
              canonical.push(href ? idFromUrl(href[1]) : null);
            }
          }
          if (Array.isArray(info) && String(info[0]) !== seed.source_item_id) failure = 'thread_identity_mismatch';
          else if (canonical.length !== 1 || canonical[0] !== seed.source_item_id) failure = 'thread_identity_mismatch';
          else if (/\bdata-page-type\s*=\s*["']SUPPORT_FORUM_THREAD["']/.test(html) &&
                   Array.isArray(thread) && thread.length >= 14 && Array.isArray(info) &&
                   typeof thread[8] === 'string' && thread[8].trim() && plain(thread[12])) {
            let published = null;
            const micros = String(info[1]);
            if (/^\d{14,17}$/.test(micros) && Number.isSafeInteger(Number(micros))) published = new Date(Number(micros)/1000).toISOString();
            // FU field 4 is the original author's public profile. Field 3 is
            // its user ID, not a comment/message ID. Replies are never visited.
            const authorName = Array.isArray(author) && Array.isArray(author[0]) &&
              String(author[2]) === String(thread[6]) && typeof author[0][0] === 'string' ? author[0][0] : null;
            question = {text:thread[12], name:thread[8], dateCreated:published, author:{name:authorName}};
            path = 'thread_view[1][12]';
          }
        } catch (_) { /* no evaluation, fallback body scraping, or reply substitution */ }
      }
    }
  }
  if (!question || !plain(question.text)) {
    outputs.push({json:{failure,source_item_id:seed.source_item_id}}); continue;
  }
  const published = question.dateCreated || question.datePublished;
  outputs.push({json:{...seed, raw_text:question.text, text_kind:'original_post',
    title:typeof question.name === 'string' ? question.name : null,
    author_name:question.author && typeof question.author.name === 'string' ? question.author.name : null,
    published_at:typeof published === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(published) ? published : null,
    collected_at:new Date().toISOString(), replies_complete:false, source_text_path:path}});
}
return outputs;
