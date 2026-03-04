async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "href") node.setAttribute("href", v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}

function render(data, query = "") {
  const meta = document.getElementById("meta");
  meta.textContent = `Fetched: ${data.fetched_at} · Items: ${data.items.length}`;

  const list = document.getElementById("list");
  list.innerHTML = "";

  const q = query.trim().toLowerCase();
  const items = q
    ? data.items.filter(x => (x.title || "").toLowerCase().includes(q))
    : data.items;

  for (const item of items) {
    const title = item.title || "";
    const price = item.price ? ` · ${item.price}` : "";
    const rank = item.rank ?? "";

    const titleNode = item.product_url
      ? el("a", { href: item.product_url, target: "_blank", rel: "noreferrer" }, [title])
      : el("span", {}, [title]);

    const li = el("li", { class: "row" }, [
      el("span", { class: "rank" }, [String(rank)]),
      el("div", { class: "main" }, [
        el("div", { class: "title" }, [titleNode]),
        el("div", { class: "price" }, [price.replace(/^ · /, "")]),
      ]),
    ]);

    list.appendChild(li);
  }
}

async function main() {
  const url = "./data/food_ranking.json";
  const data = await fetchJson(url);

  const input = document.getElementById("q");
  const reload = document.getElementById("reload");

  render(data);

  input.addEventListener("input", () => render(data, input.value));
  reload.addEventListener("click", () => location.reload());
}

main().catch(err => {
  document.getElementById("meta").textContent = `Load failed: ${err.message}`;
});
