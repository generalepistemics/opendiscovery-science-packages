export const el = <K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = '',
  text = '',
  children: Node[] = [],
): HTMLElementTagNameMap[K] => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  if (children.length > 0) node.append(...children);
  return node;
};

/** Writing the same text again still replaces the text node and lays the line out anew. */
export const setText = (node: HTMLElement, text: string): void => {
  if (node.textContent !== text) node.textContent = text;
};

/** An element drawn once for an item and updated in place while the item's key holds. */
export interface Keyed<T> {
  element: HTMLElement;
  update: (item: T) => void;
}

/**
 * Puts one element per item into `container`, in order from child `offset`
 * on. An item whose key was there last time keeps its element and gets an
 * update, so focus, hover, an open tooltip and a Stop waiting for its second
 * click all survive the next sample. The key holds everything an update
 * does not redraw. Children before `offset` and after the items stay.
 */
export const reconcile = <T>(
  container: HTMLElement,
  items: readonly T[],
  keyOf: (item: T) => string,
  create: (item: T) => Keyed<T>,
  cache: Map<string, Keyed<T>>,
  offset = 0,
): void => {
  const next = new Map<string, Keyed<T>>();
  for (const item of items) {
    let key = keyOf(item);
    // Two items with one key each keep an element of their own.
    for (let copy = 1; next.has(key); copy += 1) key = `${keyOf(item)}\u0001${copy}`;
    const reused = cache.get(key);
    if (reused) reused.update(item);
    next.set(key, reused ?? create(item));
  }
  for (const [key, entry] of cache) if (next.get(key) !== entry) entry.element.remove();
  cache.clear();
  let index = offset;
  for (const [key, entry] of next) {
    cache.set(key, entry);
    const current = container.children[index] ?? null;
    if (current !== entry.element) container.insertBefore(entry.element, current);
    index += 1;
  }
};
