function escapeHtml(str: string) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function sanitize(html: string) {
  return html.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '');
}

export function markdownToHtml(md: string) {
  const lines = md.split(/\r?\n/);
  const out: string[] = [];
  let i = 0;
  let inCode = false;
  let codeLang = '';
  let listBuffer: string[] = [];
  let olistBuffer: string[] = [];
  let tableBuffer: string[] = [];

  const flushList = () => {
    if (listBuffer.length > 0) {
      out.push(`<ul>${listBuffer.map(li => `<li>${li}</li>`).join('')}</ul>`);
      listBuffer = [];
    }
    if (olistBuffer.length > 0) {
      out.push(`<ol>${olistBuffer.map(li => `<li>${li}</li>`).join('')}</ol>`);
      olistBuffer = [];
    }
  };

  const flushTable = () => {
    if (tableBuffer.length >= 2) {
      const header = tableBuffer[0]
        .split('|')
        .map(s => s.trim())
        .filter(Boolean);
      const alignRow = tableBuffer[1]
        .split('|')
        .map(s => s.trim())
        .filter(Boolean);
      const aligns = alignRow.map(cell => {
        const start = cell.startsWith(':');
        const end = cell.endsWith(':');
        if (start && end) return 'center';
        if (end) return 'right';
        if (start) return 'left';
        return 'left';
      });
      const tbody = tableBuffer.slice(2).map(row =>
        row
          .split('|')
          .map(s => s.trim())
          .filter(Boolean)
      );
      const theadHtml = `<thead><tr>${header
        .map((h, idx) => `<th style="text-align:${aligns[idx] || 'left'}">${h}</th>`)
        .join('')}</tr></thead>`;
      const tbodyHtml = `<tbody>${tbody
        .map(
          cells => `<tr>${cells.map((c, j) => `<td style="text-align:${aligns[j] || 'left'}">${c}</td>`).join('')}</tr>`
        )
        .join('')}</tbody>`;
      out.push(`<table>${theadHtml}${tbodyHtml}</table>`);
      tableBuffer = [];
    } else if (tableBuffer.length === 1) {
      out.push(`<p>${tableBuffer[0]}</p>`);
      tableBuffer = [];
    }
  };

  const inline = (s: string) => {
    let t = s;
    t = t.replace(/!\[(.+?)\]\((.+?)\)/g, '<img src="$2" alt="$1" />');
    t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
    t = t.replace(/~~(.+?)~~/g, '<del>$1</del>');
    t = t.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/<((https?:\/\/|mailto:)[^>\s]+)>/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    t = t.replace(
      /(^|[\s(])((https?:\/\/|mailto:)[^\s)]+)(?=[\s)]|$)/g,
      '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>'
    );
    return t;
  };

  function processLines() {
    while (i < lines.length) {
      const raw = lines[i];
      if (raw.trim().startsWith('```')) {
        if (!inCode) {
          flushList();
          flushTable();
          inCode = true;
          const m = raw.trim().match(/^```(\w+)?\s*$/);
          codeLang = m && m[1] ? m[1].replace(/[^\w-]/g, '') : '';
          out.push(`<pre><code${codeLang ? ` class="language-${codeLang}"` : ''}>`);
        } else {
          inCode = false;
          codeLang = '';
          out.push('</code></pre>');
        }
        i += 1;
      } else if (inCode) {
        out.push(escapeHtml(raw));
        i += 1;
      } else if (/^\s*>/.test(raw)) {
        flushList();
        flushTable();
        const quoteLines: string[] = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          const txt = lines[i].replace(/^\s*>+\s?/, '');
          quoteLines.push(inline(txt));
          i += 1;
        }
        out.push(`<blockquote>${quoteLines.join('<br/>')}</blockquote>`);
      } else if (/^(#{1,6})\s+(.*)$/.test(raw)) {
        flushList();
        flushTable();
        const mm = raw.match(/^(#{1,6})\s+(.*)$/);
        const level = mm ? mm[1].length : 1;
        const text = mm ? mm[2] : raw;
        out.push(`<h${level}>${inline(text)}</h${level}>`);
        i += 1;
      } else if (/^\s*-\s+/.test(raw)) {
        flushTable();
        if (/^\s*-\s+\[[ xX]\]\s+/.test(raw)) {
          const checked = /\[[xX]\]/.test(raw);
          const text = raw.replace(/^\s*-\s+\[[ xX]\]\s+/, '');
          listBuffer.push(`<input type="checkbox" disabled ${checked ? 'checked' : ''}/><span>${inline(text)}</span>`);
        } else {
          listBuffer.push(inline(raw.replace(/^\s*-\s+/, '')));
        }
        i += 1;
      } else if (/^\s*\d+\.\s+/.test(raw)) {
        flushTable();
        olistBuffer.push(inline(raw.replace(/^\s*\d+\.\s+/, '')));
        i += 1;
      } else if (raw.includes('|')) {
        tableBuffer.push(raw);
        i += 1;
      } else if (raw.trim() === '') {
        flushList();
        out.push('<br/>');
        i += 1;
      } else {
        handleParagraph(raw);
        i += 1;
      }
    }
  }

  function handleParagraph(raw: string) {
    const text = inline(raw);
    // If it looks like a block-level HTML tag (e.g. from Tiptap output), don't wrap in <p>
    if (/^\s*<(?:p|div|h[1-6]|ul|ol|blockquote|table|pre|hr|img)/i.test(text)) {
      out.push(text);
    } else {
      out.push(`<p>${text}</p>`);
    }
  }

  processLines();

  flushList();
  flushTable();
  return sanitize(out.join('\n'));
}
