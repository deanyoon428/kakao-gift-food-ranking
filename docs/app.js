async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

function fmtFetched(iso) {
  if (!iso) return "-";
  return iso.replace("T", " ").replace("Z", "Z");
}

function norm(s) {
  return (s || "").toString().trim();
}

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}

function renderCategory(snapshot) {
  const meta = document.getElementById("cat_meta");
  const list = document.getElementById("cat_list");
  const delta = document.getElementById("cat_delta");
  list.innerHTML = "";
  delta.innerHTML = "";

  const fetched = snapshot?.fetched_at;
  const counts = snapshot?.category_counts || {};
  const deltas = snapshot?.category_deltas_vs_prev || {};

  meta.textContent = `Fetched: ${fmtFetched(fetched)} · Top${snapshot?.top_n ?? 100}`;

  const top = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0, 12);
  for (const [k, v] of top) {
    list.appendChild(
      el("li", {}, [
        el("span", { class: "k" }, [k]),
        el("span", { class: "v" }, [String(v)]),
      ])
    );
  }

  const changed = Object.entries(deltas).filter(([,v]) => v !== 0)
    .sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 12);

  if (!changed.length) {
    delta.appendChild(el("li", {}, [el("span",{class:"k"},["변동 없음"]), el("span",{class:"v"},["0"])]));
  } else {
    for (const [k, v] of changed) {
      delta.appendChild(
        el("li", {}, [
          el("span", { class: "k" }, [k]),
          el("span", { class: "v" }, [v > 0 ? `+${v}` : String(v)]),
        ])
      );
    }
  }
}

function renderRanking(kakao, query = "") {
  const meta = document.getElementById("kakao_meta");
  const list = document.getElementById("kakao_list");
  list.innerHTML = "";

  const fetched = kakao?.fetched_at;
  const items = kakao?.items || [];
  meta.textContent = `Fetched: ${fmtFetched(fetched)} · Items: ${items.length}`;

  const q = query.toLowerCase();
  const filtered = items
    .filter(it => !q || norm(it.title).toLowerCase().includes(q))
    .filter(it => typeof it.rank === "number" && it.rank <= 100)
    .sort((a,b) => a.rank - b.rank);

  for (const it of filtered) {
    const title = norm(it.title);
    const url = it.product_url || null;
    const price = norm(it.price);

    const titleNode = url
      ? el("a", { href: url, target: "_blank", rel: "noreferrer" }, [title])
      : el("span", {}, [title]);

    list.appendChild(
      el("li", {}, [
        el("div", { class: "badge" }, [String(it.rank)]),
        el("div", { class: "main" }, [
          el("div", { class: "title" }, [titleNode]),
          el("div", { class: "subline" }, [price || ""]),
        ]),
      ])
    );
  }
}

function renderMovers(kakao) {
  // ✅ 현재 데이터만으로는 "직전 대비"를 계산할 수 없으므로
  // 여기서는 일단 "Top100에서 눈에 띄는 키워드/상품" 영역으로 비워두지 않고,
  // 다음 단계(직전 스냅샷도 웹에 저장)를 위한 자리로 만든다.
  // 지금은 placeholders.
  const meta = document.getElementById("mv_meta");
  const up = document.getElementById("mv_up");
  const down = document.getElementById("mv_down");
  up.innerHTML = "";
  down.innerHTML = "";
  meta.textContent = "정확한 Δ랭킹은 직전 스냅샷을 함께 저장하면 표시됩니다.";

  up.appendChild(el("li", {}, [el("span",{class:"k"},["(옵션) 직전 대비 상승 Top N"]), el("span",{class:"v"},["-"])]));
  down.appendChild(el("li", {}, [el("span",{class:"k"},["(옵션) 직전 대비 하락 Top N"]), el("span",{class:"v"},["-"])]));
}

async function main() {
  const meta = document.getElementById("meta");
  const input = document.getElementById("q");
  const reload = document.getElementById("reload");

  const kakaoUrl = "./data/food_ranking.json";
  const catUrl = "./data/category_snapshot.json";

  let kakao = null;
  let cat = null;

  try {
    [kakao, cat] = await Promise.all([
      fetchJson(kakaoUrl),
      fetchJson(catUrl).catch(() => null),
    ]);

    meta.textContent =
      `Kakao fetched: ${fmtFetched(kakao?.fetched_at)} · Category fetched: ${fmtFetched(cat?.fetched_at)}`;
  } catch (e) {
    meta.textContent = `Load failed: ${e.message}`;
    return;
  }

  function rerender() {
    const q = input.value || "";
    renderRanking(kakao, q);
    if (cat) renderCategory(cat);
    renderMovers(kakao);
  }

  rerender();
  input.addEventListener("input", rerender);
  reload.addEventListener("click", () => location.reload());
}

main();
