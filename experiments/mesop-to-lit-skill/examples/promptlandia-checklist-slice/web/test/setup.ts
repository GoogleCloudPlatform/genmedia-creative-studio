// happy-dom defines an own `nodeName` getter on `Node.prototype` that returns
// `''` and overrides it on subclasses (`Element.prototype`, `Text.prototype`,
// etc.), whereas real browsers only define `nodeName` on `Node.prototype`.
// DOMPurify >=3.4.17 looks up `Object.getOwnPropertyDescriptor(Node.prototype, 'nodeName')`
// at module initialization, so under happy-dom it receives `''` for every
// element unless `Node.prototype.nodeName` delegates to the subclass getter.
if (typeof Node !== 'undefined') {
  Object.defineProperty(Node.prototype, 'nodeName', {
    configurable: true,
    get() {
      for (
        let proto = Object.getPrototypeOf(this);
        proto && proto !== Node.prototype;
        proto = Object.getPrototypeOf(proto)
      ) {
        const desc = Object.getOwnPropertyDescriptor(proto, 'nodeName');
        if (desc?.get) return desc.get.call(this);
      }
      return '';
    },
  });
}
