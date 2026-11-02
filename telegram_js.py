MESSAGE_EXTRACTOR_JS = """
(limit) => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const attr = (el, names) => {
    for (const name of names) {
      const value = el.getAttribute(name);
      if (value) return value;
    }
    return '';
  };
  const timestampMs = (messageEl, timeEl) => {
    const names = ['data-timestamp', 'data-date', 'datetime', 'title', 'aria-label'];
    const raw = attr(timeEl || messageEl, names) || attr(messageEl, names);
    if (!raw) return null;
    const numeric = Number(raw);
    if (Number.isFinite(numeric) && numeric > 0) {
      return numeric < 100000000000 ? numeric * 1000 : numeric;
    }
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) return parsed;
    return null;
  };
  const textFromNode = (node) => {
    if (!node) return '';
    const clone = node.cloneNode(true);
    clone.querySelectorAll('time,.time,.message-time,.reactions,.peer-title,.colored-name,.name')
      .forEach((child) => child.remove());
    return normalize(clone.innerText);
  };
  const messageText = (el) => {
    const candidates = [
      el.querySelector('.message .translatable-message'),
      el.querySelector('.message .text-content'),
      el.querySelector('.message'),
      el.querySelector('.text-content'),
    ];
    for (const candidate of candidates) {
      const text = textFromNode(candidate);
      if (text) return text;
    }
    return textFromNode(el);
  };
  const primary = Array.from(document.querySelectorAll(
    '[data-mid], [data-message-id], [data-message-id-id]'
  ));
  const fallback = Array.from(document.querySelectorAll('.Message, .message, .message-list-item'));
  const nodes = primary.length ? primary : fallback;
  const uniqueNodes = [];
  const seen = new Set();
  for (const node of nodes) {
    if (!node || seen.has(node)) continue;
    seen.add(node);
    uniqueNodes.push(node);
  }
  return uniqueNodes.slice(-limit).map((el, index) => {
    const timeNode = el.querySelector('time, .time, [datetime]');
    const senderNode = el.querySelector('.colored-name .peer-title, .peer-title, .message-title');
    const className = String(el.className || '');
    const text = messageText(el);
    const messageKey = attr(el, ['data-mid', 'data-message-id', 'data-id', 'id']);
    return {
      index,
      message_key: messageKey,
      text,
      sender_name: normalize(senderNode ? senderNode.innerText : ''),
      timestamp_ms: timestampMs(el, timeNode),
      outgoing: /(^|\\s)(own|out|is-out|message-out)(\\s|$)/i.test(className),
    };
  }).filter((item) => item.text);
}
"""

SCROLL_TO_LATEST_JS = """
() => {
  const selectors = ['#column-center .scrollable-y', '.bubbles-inner', '.bubbles'];
  for (const selector of selectors) {
    for (const node of document.querySelectorAll(selector)) {
      if (node && node.scrollHeight > node.clientHeight) {
        node.scrollTop = node.scrollHeight;
      }
    }
  }
  window.scrollTo(0, document.body.scrollHeight);
}
"""
