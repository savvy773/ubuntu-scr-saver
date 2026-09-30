import { quoteLibrary } from './quote-library';
export const quotes = quoteLibrary.map(([text]) => text);

const modals = new Set(['can', 'cannot', "can't", 'could', 'may', 'might', 'must', 'should', 'would', 'will', "won't"]);
const helpers = new Set(['have', 'has', 'had', 'be', 'is', 'are', 'was', 'were', 'been', 'being']);
const doHelpers = new Set(['do', 'does', 'did', "don't", "doesn't", "didn't"]);
const adverbs = new Set(['not', 'never', 'already', 'just', 'still', 'also', 'often', 'sometimes', 'quietly', 'fully', 'carefully', 'eventually', 'usually', 'immediately', 'repeatedly']);
const participles = new Set(['made', 'known', 'built', 'done', 'taught', 'gone', 'shown', 'seen', 'given', 'chosen', 'kept', 'lost', 'held', 'found', 'thought', 'become', 'understood', 'written', 'taken', 'grown', 'brought', 'left', 'read', 'begun']);
const connectors = new Set(['because', 'although', 'while', 'whenever', 'when', 'if', 'unless', 'until', 'whether']);
const prepositions = new Set(['in', 'on', 'at', 'of', 'for', 'from', 'with', 'without', 'by', 'to', 'into', 'through', 'during', 'within', 'beyond', 'between', 'among', 'toward', 'towards', 'against', 'across', 'under', 'over', 'upon', 'around', 'throughout', 'despite']);

function followingWord(index: number, tokens: string[]) {
  return tokens.slice(index + 1).map(token => token.toLowerCase())
    .find(word => /^[a-z]/.test(word) && !adverbs.has(word));
}

function isAuxiliary(word: string, index: number, tokens: string[], forms: Set<string>) {
  if (modals.has(word) || doHelpers.has(word)) return true;
  if (!helpers.has(word)) return false;
  for (let next = index + 1; next < tokens.length; next++) {
    const candidate = tokens[next].toLowerCase();
    if (!/^[a-z]/.test(candidate) || adverbs.has(candidate)) continue;
    // A following participle makes have/be auxiliary; a linking or possessive
    // use remains a main verb, as in "is useful" or "have a chance".
    return forms.has(candidate) &&
      (participles.has(candidate) || candidate.endsWith('ed') || candidate.endsWith('ing') || candidate === 'been');
  }
  return false;
}

function fitQuote(element: HTMLElement) {
  element.style.fontSize = '';
  const parent = element.parentElement!;
  const parentStyle = getComputedStyle(parent);
  const available = parent.clientHeight - parseFloat(parentStyle.paddingTop) - parseFloat(parentStyle.paddingBottom);
  let size = parseFloat(getComputedStyle(element).fontSize);
  for (let attempt = 0; attempt < 5; attempt++) {
    const widest = Math.max(...Array.from(element.children).map(line => line.scrollWidth));
    if (widest <= element.clientWidth && element.offsetHeight <= available) break;
    const ratio = Math.min(element.clientWidth / widest, available / element.offsetHeight, 1);
    if (ratio >= 1 || size <= 8) break;
    size = Math.max(8, size * ratio * 0.98);
    element.style.fontSize = `${size}px`;
  }
}

function lineBreak(text: string) {
  const words = text.match(/\S+\s*/g) ?? [];
  const target = text.length / 2;
  const awkwardEnd = new Set(['a', 'an', 'the', 'of', 'to', 'with', 'in', 'on', 'for', 'and', 'or', 'your', 'their', ...modals, ...helpers]);
  let best = 0;
  let bestScore = Infinity;
  for (let cut = 4; cut <= words.length - 4; cut++) {
    const first = words.slice(0, cut).join('');
    const second = words.slice(cut).join('');
    let score = (first.trim().length - target) ** 2 + (second.trim().length - target) ** 2;
    if (/[,;:]$/.test(first.trim())) score -= 120;
    if (awkwardEnd.has(first.trim().split(/\s+/).at(-1)!.toLowerCase())) score += 180;
    if (score < bestScore) {
      bestScore = score;
      best = first.length;
    }
  }
  return best;
}

function renderQuote(element: HTMLElement, text: string, verbs: string) {
  const fragment = document.createDocumentFragment();
  const forms = new Set(verbs.split(' '));
  const tokens = text.match(/[A-Za-z]+(?:'[A-Za-z]+)?|[^A-Za-z]+/g) ?? [];
  const split = lineBreak(text);
  const lines = Array.from({ length: 2 }, () => {
    const line = document.createElement('span');
    line.className = 'quote-line';
    fragment.append(line);
    return line;
  });
  let offset = 0;
  for (const [index, token] of tokens.entries()) {
    const line = lines[offset >= split ? 1 : 0];
    const word = token.toLowerCase();
    let kind = '';
    if (forms.has(word)) kind = isAuxiliary(word, index, tokens, forms) ? 'auxiliary' : 'main-verb';
    else if (connectors.has(word)) kind = 'connector';
    else if (prepositions.has(word) && !(word === 'to' && forms.has(followingWord(index, tokens) ?? ''))) kind = 'preposition';
    if (kind) {
      const span = document.createElement('span');
      span.className = `quote-word ${kind}`;
      span.textContent = token;
      line.append(span);
    } else {
      line.append(document.createTextNode(token));
    }
    offset += token.length;
  }
  element.replaceChildren(fragment);
  requestAnimationFrame(() => fitQuote(element));
}

const quoteElement = document.getElementById('quoteText')!;
new ResizeObserver(() => fitQuote(quoteElement)).observe(quoteElement.parentElement!);
document.fonts.ready.then(() => fitQuote(quoteElement));

(() => {
  const intervalMs = 10 * 60 * 1000;
  const storageKey = 'screensaver-reflections-v2';
  const quoteEl = document.getElementById('quoteText')!;
  let timer: ReturnType<typeof setTimeout>;
  let state: { order: number[]; position: number; nextChangeAt: number } =
    { order: [], position: 0, nextChangeAt: 0 };

  function shuffledOrder(previousIndex?: number) {
    const order = quotes.map((_, index) => index);
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    if (order[0] === previousIndex && order.length > 1) {
      [order[0], order[1]] = [order[1], order[0]];
    }
    return order;
  }

  try {
    state = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
  } catch (_) {
    // Rotation still works when browser storage is unavailable.
  }

  if (!state || !Array.isArray(state.order) || state.order.length !== quotes.length ||
      new Set(state.order).size !== quotes.length ||
      !state.order.every(i => Number.isInteger(i) && i >= 0 && i < quotes.length) ||
      !Number.isInteger(state.position) || state.position < 0 || state.position >= quotes.length ||
      !Number.isFinite(state.nextChangeAt)) {
    state = { order: shuffledOrder(), position: 0, nextChangeAt: Date.now() + intervalMs };
  }

  function updateQuote() {
    clearTimeout(timer);
    const now = Date.now();
    if (now >= state.nextChangeAt) {
      const previousIndex = state.order[state.position];
      state.position++;
      if (state.position >= state.order.length) {
        state.order = shuffledOrder(previousIndex);
        state.position = 0;
      }
      state.nextChangeAt = now + intervalMs;
    }

    const text = `“${quotes[state.order[state.position]]}”`;
    if (quoteEl.textContent !== text) {
      renderQuote(quoteEl, text, quoteLibrary[state.order[state.position]][1]);
      quoteEl.classList.remove('changing');
      void quoteEl.offsetWidth;
      quoteEl.classList.add('changing');
    }

    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
    } catch (_) {
      // Keep the in-memory sequence if storage is unavailable.
    }
    timer = setTimeout(updateQuote, Math.min(intervalMs, Math.max(1, state.nextChangeAt - now)));
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) updateQuote();
  });
  updateQuote();
})();
