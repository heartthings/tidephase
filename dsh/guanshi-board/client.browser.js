window.__ModuleLoader__.load({id: "guanshi-board", factory: function (require) {
  const React = require("react");
  const { useEffect, useRef, useState } = React;
  const h = React.createElement;
  const module = { exports: {} };

  const SESSIONS = [
    { id: "preopen", label: "盘前" },
    { id: "intraday", label: "盘中" },
    { id: "afterclose", label: "盘后" }
  ];
  const CATALOG = {
    preopen: [
      { type: "preopen-messages", title: "盘前消息" },
      { type: "overnight", title: "隔夜外盘" }
    ],
    intraday: [
      { type: "index-board", title: "指数涨跌" },
      { type: "breadth-board", title: "涨跌分布" },
      { type: "sentiment-dial", title: "赚钱效应" },
      { type: "overnight", title: "隔夜外盘" },
      { type: "minute-board", title: "指数分钟" },
      { type: "hour-board", title: "指数小时成交" },
      { type: "sector-board", title: "板块涨跌与资金" },
      { type: "leader-board", title: "领涨领跌" },
      { type: "auction-board", title: "竞价强弱" },
      { type: "market-radar", title: "市场雷达" },
      { type: "market-dynamics", title: "市场动态" },
      { type: "news-board", title: "快讯" },
      { type: "wire-board", title: "电报与催化" },
      { type: "predict-board", title: "预测与反思" },
      { type: "coverage-board", title: "数据覆盖" }
    ],
    afterclose: [
      { type: "sentiment-dial", title: "情绪刻度" },
      { type: "theme-stage", title: "题材舞台" },
      { type: "reason-check", title: "原因核对" },
      { type: "money-flow", title: "资金去向" },
      { type: "limit-cards", title: "涨停与跌停" },
      { type: "next-candidates", title: "次日候选" },
      { type: "fulfillment", title: "预测兑现" },
      { type: "tomorrow-line", title: "明日一句" }
    ]
  };
  const DEFAULT_SPEC = {
    version: 1,
    sessions: {
      preopen: { boards: [
        { id: "preopen-messages-1", type: "preopen-messages", x: 24, y: 24, w: 1120, h: 700 }
      ] },
      intraday: { boards: [
        { id: "index-board-1", type: "index-board", x: 24, y: 24, w: 380, h: 280 },
        { id: "breadth-board-1", type: "breadth-board", x: 420, y: 24, w: 360, h: 280 },
        { id: "sentiment-dial-1", type: "sentiment-dial", x: 796, y: 24, w: 380, h: 280 },
        { id: "minute-board-1", type: "minute-board", x: 24, y: 320, w: 560, h: 300 },
        { id: "hour-board-1", type: "hour-board", x: 600, y: 320, w: 576, h: 300 },
        { id: "sector-board-1", type: "sector-board", x: 24, y: 636, w: 560, h: 340 },
        { id: "leader-board-1", type: "leader-board", x: 600, y: 636, w: 576, h: 340 },
        { id: "auction-board-1", type: "auction-board", x: 24, y: 992, w: 360, h: 300 },
        { id: "overnight-1", type: "overnight", x: 400, y: 992, w: 360, h: 300 },
        { id: "news-board-1", type: "news-board", x: 776, y: 992, w: 400, h: 300 },
        { id: "market-radar-1", type: "market-radar", x: 24, y: 1308, w: 560, h: 360 },
        { id: "market-dynamics-1", type: "market-dynamics", x: 600, y: 1308, w: 576, h: 360 },
        { id: "wire-board-1", type: "wire-board", x: 24, y: 1684, w: 560, h: 280 },
        { id: "predict-board-1", type: "predict-board", x: 600, y: 1684, w: 576, h: 280 },
        { id: "coverage-board-1", type: "coverage-board", x: 24, y: 1980, w: 1152, h: 280 }
      ] },
      afterclose: { boards: [
        { id: "sentiment-dial-1", type: "sentiment-dial", x: 24, y: 24, w: 1152, h: 180 },
        { id: "theme-stage-1", type: "theme-stage", x: 24, y: 228, w: 720, h: 360 },
        { id: "tomorrow-line-1", type: "tomorrow-line", x: 776, y: 228, w: 400, h: 168 },
        { id: "money-flow-1", type: "money-flow", x: 776, y: 420, w: 400, h: 168 },
        { id: "reason-check-1", type: "reason-check", x: 24, y: 612, w: 560, h: 320 },
        { id: "limit-cards-1", type: "limit-cards", x: 616, y: 612, w: 560, h: 320 },
        { id: "next-candidates-1", type: "next-candidates", x: 24, y: 956, w: 720, h: 340 },
        { id: "fulfillment-1", type: "fulfillment", x: 776, y: 956, w: 400, h: 340 }
      ] }
    }
  };
  const TITLES = Object.values(CATALOG).flat().reduce((map, item) => {
    map[item.type] = item.title;
    return map;
  }, {});
  const STAGES = ["聚集未完成", "启动", "发酵", "高潮", "分歧", "退潮"];

  const DEMO = {
    date: "2026-11-03",
    rail: [
      { hour: "08:00", count: 12 },
      { hour: "10:00", count: 18 },
      { hour: "14:00", count: 9 },
      { hour: "20:00", count: 15 },
      { hour: "22:00", count: 7 }
    ],
    cards: [
      {
        theme: "商业航天",
        count: 6,
        summary: "卫星互联网再出进展，昨夜几家相关公司跟进",
        items: [
          { id: "m1", time: "21:14", title: "卫星互联网试验星组网完成", content: "卫星互联网试验星组网完成", source: "eastmoney", folded: false },
          { id: "m2", time: "19:02", title: "商业航天发射窗口确认", content: "商业航天发射窗口确认", source: "eastmoney", folded: false }
        ]
      },
      {
        theme: "锂电池",
        count: 4,
        summary: "电解液和正极材料都有新消息",
        items: [
          { id: "m3", time: "18:40", title: "电解液报价持稳", content: "电解液报价持稳", source: "eastmoney", folded: false }
        ]
      },
      {
        theme: "未归类",
        count: 3,
        summary: "央行官员表态与外围利率消息",
        items: [
          { id: "m4", time: "15:54", title: "欧洲央行管委：暂停加息不等于周期结束", content: "欧洲央行管委：暂停加息不等于周期结束", source: "eastmoney", folded: false }
        ]
      }
    ],
    total: 28,
    quotes: [
      { code: "SPX", name: "标普500", pct: -0.51 },
      { code: "IXIC", name: "纳斯达克", pct: -1.07 },
      { code: "HSI", name: "恒生指数", pct: 0.35 },
      { code: "GC", name: "纽约黄金", pct: 0.82 },
      { code: "SI", name: "纽约白银", pct: 3.27 },
      { code: "CL", name: "原油", pct: -0.44 }
    ],
    events: [
      { id: "r1", time: "10:21", stockName: "时代万恒", lbStatus: "首板", status: "封板", content: "锂电池相关封板，封单增加 12%" },
      { id: "r2", time: "09:54", stockName: "三峡新材", lbStatus: "2板", status: "回封", content: "电解液方向回封，炸板后重新钉住" },
      { id: "r3", time: "09:31", stockName: "阳光照明", lbStatus: "4板", status: "一字", content: "商业航天高标继续一字" },
      { id: "r4", time: "13:18", stockName: "某光电", lbStatus: "分歧", status: "打开", content: "高位打开，量能减少" }
    ],
    items: [
      { id: "d1", time: "14:22", stock: "sh600261", comment: "阳光照明封单减少后回补" },
      { id: "d2", time: "11:05", stock: "sh600293", comment: "三峡新材二次封板" },
      { id: "d3", time: "10:18", stock: "sz000001", comment: "大盘午后走平，题材继续分化" },
      { id: "d4", time: "09:42", stock: "sh600241", comment: "时代万恒开板后回封" }
    ],
    indices: [
      { code: "sh000001", name: "上证", close: 3284.12, pct: 0.42 },
      { code: "sz399001", name: "深成", close: 10842.55, pct: -0.21 },
      { code: "sz399006", name: "创业板", close: 2188.4, pct: -0.18 },
      { code: "sh000300", name: "沪深300", close: 3920.1, pct: 0.15 }
    ],
    breadth: {
      up: 2410, down: 2688, flat: 86,
      buckets: [
        { label: "涨停附近", count: 48 },
        { label: "强势", count: 310 },
        { label: "小涨", count: 2052 },
        { label: "小跌", count: 1980 },
        { label: "弱势", count: 620 },
        { label: "跌停附近", count: 18 }
      ]
    },
    minutes: [
      { code: "sh000001", name: "上证", points: [3270, 3274, 3280, 3276, 3282, 3288, 3284] },
      { code: "sz399006", name: "创业板", points: [2202, 2196, 2190, 2188, 2194, 2186, 2188] }
    ],
    hours: [
      { slot: "10:00", shAmount: 4200, szAmount: 5100, cyAmount: 1800, shVolume: 1.2, szVolume: 1.8, cyVolume: 0.6 },
      { slot: "11:30", shAmount: 6800, szAmount: 7900, cyAmount: 2600, shVolume: 1.9, szVolume: 2.4, cyVolume: 0.9 },
      { slot: "15:00", shAmount: 9800, szAmount: 11200, cyAmount: 4100, shVolume: 2.6, szVolume: 3.2, cyVolume: 1.3 }
    ],
    sectors: {
      gainers: [{ name: "商业航天", pct: 4.8 }, { name: "锂电池", pct: 3.1 }, { name: "军工电子", pct: 2.4 }],
      losers: [{ name: "白酒", pct: -2.6 }, { name: "半导体", pct: -1.9 }, { name: "消费电子", pct: -1.4 }],
      inflow: [{ name: "商业航天", yi: 18.6 }, { name: "锂电池", yi: 12.4 }, { name: "军工电子", yi: 8.1 }]
    },
    leaders: {
      up: [{ code: "sh600261", name: "阳光照明", pct: 10.02 }, { code: "sh600293", name: "三峡新材", pct: 9.98 }],
      down: [{ code: "sz300001", name: "某光电", pct: -9.96 }, { code: "sh600519", name: "贵州茅台", pct: -2.1 }]
    },
    auction: [
      { code: "sh600261", name: "阳光照明", pct: 6.4, sector: "商业航天" },
      { code: "sh600241", name: "时代万恒", pct: 4.1, sector: "锂电池" }
    ],
    headlines: [
      { time: "10:21", title: "商业航天方向多股封板", source: "eastmoney" },
      { time: "09:42", title: "锂电池电解液报价持稳", source: "cls" }
    ],
    wires: [
      { time: "10:18", title: "卫星互联网试验星组网完成", source: "财联社" }
    ],
    catalysts: [
      { date: "2026-11-03", level: "中", summary: "商业航天发射窗口确认" }
    ],
    predictions: {
      results: [{ result: "hit", count: 12 }, { result: "miss", count: 7 }, { result: "未核对", count: 4 }],
      recent: [{ category: "first_board", result: "hit", statement: "商业航天样本封板" }]
    },
    coverage: [
      { name: "指数日线", rows: 2400, latest: "2026-11-03" },
      { name: "个股日线", rows: 180000, latest: "2026-11-03" },
      { name: "涨停池", rows: 8600, latest: "2026-11-03" }
    ],
    jobs: [
      { job: "j_index_minute", status: "OK", count: 8, last: "11-03 15:02" },
      { job: "j_radar", status: "OK", count: 24, last: "11-03 14:55" }
    ],
    sentiment: {
      limitUp: 48,
      broken: 34,
      maxBoard: 6,
      limitDown: 18,
      sealRate: 74.2,
      premium: 1.9,
      index: [
        { code: "sh000001", name: "上证", pct: 0.42 },
        { code: "sz399006", name: "创业板", pct: -0.18 }
      ]
    },
    themes: [
      { name: "商业航天", count: 8, height: 6, stage: "高潮", verdict: "成立", line: "卫星与激光通信", push: "合力" },
      { name: "锂电池", count: 7, height: 4, stage: "发酵", verdict: "成立", line: "电解液与正极", push: "合力" },
      { name: "国有企业", count: 12, height: 2, stage: "聚集未完成", verdict: "口袋", line: "混进别的主因", push: "主力" },
      { name: "股权转让", count: 5, height: 3, stage: "启动", verdict: "口袋", line: "各说各的", push: "主力" },
      { name: "光纤概念", count: 4, height: 5, stage: "分歧", verdict: "成立", line: "光模块回落", push: "主力" }
    ],
    industries: [
      { name: "电力设备", count: 9 },
      { name: "国防军工", count: 6 },
      { name: "电子", count: 5 }
    ],
    reasons: [
      { name: "商业航天", verdict: "成立", line: "卫星互联网 + 激光通信", count: 8 },
      { name: "锂电池", verdict: "成立", line: "电解液报价稳住", count: 7 },
      { name: "国有企业", verdict: "口袋", line: "原因原文各说各的", count: 12 },
      { name: "光纤概念", verdict: "成立", line: "光模块分歧后留强", count: 4 }
    ],
    money: {
      inflow: [
        { name: "商业航天", yi: 18.6 },
        { name: "锂电池", yi: 12.4 },
        { name: "军工电子", yi: 8.1 }
      ],
      outflow: [
        { name: "半导体", yi: -9.4 },
        { name: "消费电子", yi: -6.2 },
        { name: "白酒", yi: -4.8 }
      ]
    },
    limitCards: {
      up: [
        { name: "阳光照明", code: "sh600261", theme: "商业航天", height: 4, push: "合力", line: "商业航天 + 激光通信", side: "up" },
        { name: "三峡新材", code: "sh600293", theme: "锂电池", height: 2, push: "合力", line: "电解液相关", side: "up" },
        { name: "时代万恒", code: "sh600241", theme: "锂电池", height: 1, push: "主力", line: "镍氢电池", side: "up" }
      ],
      down: [
        { name: "某光电", code: "sz300001", theme: "光纤概念", height: 1, push: "主力", line: "高位兑现", side: "down" }
      ]
    },
    candidates: {
      first: [
        { theme: "商业航天", people: [{ name: "样本A", code: "sz300101", prob: 28 }, { name: "样本B", code: "sh601101", prob: 21 }] },
        { theme: "锂电池", people: [{ name: "样本C", code: "sz002201", prob: 19 }] }
      ],
      second: [
        { theme: "商业航天", people: [{ name: "样本D", code: "sh600261", prob: 34 }] }
      ]
    },
    fulfillment: {
      shown: [
        { name: "样本甲", theme: "商业航天", prob: 31, result: "hit", bars: [1.2, -0.4, 2.1, 3.4, 5.1, 9.9, 4.2, 1.1] },
        { name: "样本乙", theme: "锂电池", prob: 22, result: "miss", bars: [2.0, 1.1, -1.4, -3.2, 0.5, -2.1, 1.0, -0.8] },
        { name: "样本丙", theme: "光纤概念", prob: 18, result: "hit", bars: [-1.1, 0.4, 1.8, 2.2, 3.0, 4.5, 2.1, 0.6] }
      ],
      quietMisses: 4
    },
    tomorrow: {
      status: "中性",
      chips: ["按题材条件", "买在分歧", "不因指数改纪律"]
    }
  };

  function apiBase() {
    try {
      return localStorage.getItem("guanshi.api") || "http://127.0.0.1:8787";
    } catch (error) {
      return "http://127.0.0.1:8787";
    }
  }

  function todayISO() {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }

  async function readJSON(path) {
    const response = await fetch(apiBase() + path);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function BoardPanel(props) {
    const [session, setSession] = useState("afterclose");
    const [date, setDate] = useState(todayISO());
    const [spec, setSpec] = useState(DEFAULT_SPEC);
    const [menu, setMenu] = useState(null);
    const [narrow, setNarrow] = useState(window.innerWidth < 840);
    const [scheme, setScheme] = useState(initialScheme);
    const [payload, setPayload] = useState(DEMO);
    const [gaps, setGaps] = useState([]);
    const [usingDemo, setUsingDemo] = useState(true);
    const dragRef = useRef(false);
    const specRef = useRef(spec);
    specRef.current = spec;

    useEffect(() => {
      const media = window.matchMedia("(max-width: 840px)");
      const onResize = () => setNarrow(media.matches);
      media.addEventListener("change", onResize);
      return () => media.removeEventListener("change", onResize);
    }, []);

    useEffect(() => {
      let stop = false;
      readJSON("/api/public/v1/boards/spec").then((body) => {
        if (!stop && body && body.data && body.data.sessions) setSpec(body.data);
      }).catch(() => {});
      return () => { stop = true; };
    }, []);

    useEffect(() => {
      let stop = false;
      const pull = () => {
        if (dragRef.current) return;
        readJSON("/api/public/v1/boards/spec").then((body) => {
          if (stop || dragRef.current || !body || !body.data) return;
          if (JSON.stringify(body.data) !== JSON.stringify(specRef.current)) setSpec(body.data);
        }).catch(() => {});
      };
      const timer = window.setInterval(pull, 5000);
      return () => { stop = true; window.clearInterval(timer); };
    }, []);

    useEffect(() => {
      let stop = false;
      const load = () => {
        const jobs = endpoints(session, date).map((path) => readJSON(path).catch(() => ({ ok: false })));
        Promise.all(jobs).then((bodies) => {
          if (stop) return;
          const next = {};
          const notes = [];
          let live = false;
          bodies.forEach((body) => {
            if (!body || body.ok === false) return;
            live = true;
            Object.assign(next, body.data || {});
            (body.gaps || []).forEach((gap) => notes.push(gap));
          });
          if (!live || Object.keys(next).length === 0) {
            setPayload(DEMO);
            setUsingDemo(true);
            setGaps(["当前使用示例数据"]);
            return;
          }
          setPayload(Object.assign({}, DEMO, next));
          setUsingDemo(false);
          setGaps(Array.from(new Set(notes)));
        });
      };
      load();
      const timer = window.setInterval(load, session === "intraday" ? 120000 : 60000);
      return () => { stop = true; window.clearInterval(timer); };
    }, [session, date]);

    const boards = (spec.sessions[session] && spec.sessions[session].boards) || [];
    const canvasHeight = Math.max(760, ...boards.map((board) => board.y + board.h + 48));

    function commit(next) {
      setSpec(next);
      specRef.current = next;
      try { localStorage.setItem("guanshi.spec", JSON.stringify(next)); } catch (error) {}
      fetch(apiBase() + "/api/public/v1/boards/spec", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(next)
      }).catch(() => {});
    }

    function patchBoard(id, change) {
      commit({
        ...spec,
        sessions: {
          ...spec.sessions,
          [session]: {
            boards: boards.map((board) => board.id === id ? { ...board, ...change } : board)
          }
        }
      });
    }

    function addBoard(type, x, y) {
      const board = {
        id: type + "-" + Date.now().toString(36),
        type: type,
        x: Math.max(24, x),
        y: Math.max(24, y),
        w: type === "sentiment-dial" ? 980 : 420,
        h: type === "sentiment-dial" ? 180 : 320
      };
      commit({
        ...spec,
        sessions: {
          ...spec.sessions,
          [session]: { boards: boards.concat(board) }
        }
      });
      setMenu(null);
    }

    function removeBoard(id) {
      commit({
        ...spec,
        sessions: {
          ...spec.sessions,
          [session]: { boards: boards.filter((board) => board.id !== id) }
        }
      });
      setMenu(null);
    }

    function onCanvasMenu(event) {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      setMenu({
        x: event.clientX,
        y: event.clientY,
        dropX: event.clientX - rect.left + event.currentTarget.scrollLeft,
        dropY: event.clientY - rect.top + event.currentTarget.scrollTop
      });
    }

    function switchScheme(next) {
      setScheme(next);
      if (props.setScheme) props.setScheme(next);
    }

    return h("div", { className: "gs", "data-scheme": scheme, "data-session": session },
      h(Style),
      h("header", { className: "gs-top" },
        h("div", { className: "gs-brand" },
          h("strong", null, "观势"),
          h("span", null, "仅 A 股")
        ),
        h("nav", { className: "gs-tabs", "aria-label": "时段" }, SESSIONS.map((item) => h("button", {
          key: item.id,
          type: "button",
          className: session === item.id ? "is-on" : "",
          onClick: () => setSession(item.id)
        }, item.label))),
        h("input", {
          className: "gs-date",
          type: "date",
          value: date,
          onChange: (event) => setDate(event.target.value)
        }),
        h("div", { className: "gs-scheme", "aria-label": "配色" }, ["light", "dark"].map((item) => h("button", {
          key: item,
          type: "button",
          className: scheme === item ? "is-on" : "",
          onClick: () => switchScheme(item)
        }, item === "light" ? "浅色" : "深色")))
      ),
      h("p", { className: "gs-risk" }, "数据会延迟，模型会说错。这不是投资建议。"),
      usingDemo ? h("p", { className: "gs-gap" }, "示例数据已打开。接口恢复后会自动换成真实数据。") : null,
      gaps.filter((gap) => gap !== "当前使用示例数据").map((gap) => h("p", { key: gap, className: "gs-gap" }, gap)),
      h("div", {
        className: narrow ? "gs-canvas is-narrow" : "gs-canvas",
        style: narrow ? null : { height: canvasHeight },
        onContextMenu: onCanvasMenu,
        onClick: () => setMenu(null)
      }, boards.map((board) => h(Frame, {
        key: board.id,
        board: board,
        narrow: narrow,
        payload: payload,
        onChange: (change) => patchBoard(board.id, change),
        onRemove: () => removeBoard(board.id),
        onMenu: (event) => {
          event.preventDefault();
          event.stopPropagation();
          setMenu({ x: event.clientX, y: event.clientY, dropX: board.x + 24, dropY: board.y + 24, target: board.id });
        },
        setDragging: (value) => { dragRef.current = value; }
      }))),
      menu ? h("div", {
        className: "gs-menu",
        style: { left: menu.x, top: menu.y },
        onClick: (event) => event.stopPropagation(),
        onContextMenu: (event) => event.preventDefault()
      },
        h("p", null, "添加看板"),
        CATALOG[session].map((item) => h("button", {
          key: item.type,
          type: "button",
          onClick: () => addBoard(item.type, menu.dropX, menu.dropY)
        }, item.title)),
        menu.target ? h("button", { type: "button", className: "is-danger", onClick: () => removeBoard(menu.target) }, "移走这块") : null
      ) : null
    );
  }

  function initialScheme() {
    if (document.body && document.body.hasAttribute("data-ds-dark-theme")) return "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function endpoints(session, date) {
    const q = "?date=" + encodeURIComponent(date);
    if (session === "preopen") return ["/api/public/v1/preopen/messages" + q, "/api/public/v1/preopen/overnight" + q];
    if (session === "intraday") {
      return [
        "/api/public/v1/intraday/radar" + q,
        "/api/public/v1/intraday/dynamics" + q,
        "/api/public/v1/intraday/tape" + q
      ];
    }
    return ["/api/public/v1/afterclose/review" + q];
  }

  function Frame(props) {
    const board = props.board;
    const style = props.narrow ? null : { left: board.x, top: board.y, width: board.w, height: board.h };
    return h("section", {
      className: "gs-frame",
      style: style,
      onContextMenu: props.onMenu
    },
      h("header", {
        className: "gs-frame-title",
        onPointerDown: (event) => startDrag(event, board, props)
      },
        h("div", { className: "gs-frame-label" },
          h("span", { className: "gs-dot", "aria-hidden": "true" }),
          h("strong", null, TITLES[board.type] || board.type)
        ),
        h("button", { type: "button", "aria-label": "移走这块看板", onClick: props.onRemove }, "×")
      ),
      h("div", { className: "gs-frame-body" }, h(Body, { type: board.type, payload: props.payload })),
      props.narrow ? null : ["n", "s", "e", "w", "se"].map((edge) => h("i", {
        key: edge,
        className: "gs-handle gs-handle-" + edge,
        onPointerDown: (event) => startResize(event, edge, board, props)
      }))
    );
  }

  function startDrag(event, board, props) {
    if (event.button !== 0 || props.narrow) return;
    event.preventDefault();
    event.stopPropagation();
    props.setDragging(true);
    const ox = event.clientX;
    const oy = event.clientY;
    const move = (ev) => props.onChange({
      x: Math.max(0, Math.round(board.x + ev.clientX - ox)),
      y: Math.max(0, Math.round(board.y + ev.clientY - oy))
    });
    const up = () => {
      props.setDragging(false);
      window.removeEventListener("pointermove", move);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  function startResize(event, edge, board, props) {
    event.preventDefault();
    event.stopPropagation();
    props.setDragging(true);
    const ox = event.clientX;
    const oy = event.clientY;
    const move = (ev) => {
      const dx = ev.clientX - ox;
      const dy = ev.clientY - oy;
      const next = { x: board.x, y: board.y, w: board.w, h: board.h };
      if (edge.includes("e")) next.w = clamp(board.w + dx, 240, 1600);
      if (edge.includes("s")) next.h = clamp(board.h + dy, 160, 1200);
      if (edge.includes("w")) {
        next.w = clamp(board.w - dx, 240, 1600);
        next.x = board.x + (board.w - next.w);
      }
      if (edge.includes("n")) {
        next.h = clamp(board.h - dy, 160, 1200);
        next.y = board.y + (board.h - next.h);
      }
      props.onChange(next);
    };
    const up = () => {
      props.setDragging(false);
      window.removeEventListener("pointermove", move);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, Math.round(value)));
  }

  function Body(props) {
    const data = props.payload || DEMO;
    switch (props.type) {
      case "preopen-messages": return h(Messages, { data: data });
      case "overnight": return h(Overnight, { data: data });
      case "market-radar": return h(Radar, { events: data.events || DEMO.events });
      case "market-dynamics": return h(Dynamics, { items: data.items || DEMO.items });
      case "index-board": return h(IndexBoard, { rows: data.indices || DEMO.indices });
      case "breadth-board": return h(BreadthBoard, { breadth: data.breadth || DEMO.breadth });
      case "minute-board": return h(MinuteBoard, { rows: data.minutes || DEMO.minutes });
      case "hour-board": return h(HourBoard, { rows: data.hours || DEMO.hours });
      case "sector-board": return h(SectorBoard, { sectors: data.sectors || DEMO.sectors });
      case "leader-board": return h(LeaderBoard, { leaders: data.leaders || DEMO.leaders });
      case "auction-board": return h(AuctionBoard, { rows: data.auction || DEMO.auction });
      case "news-board": return h(LineList, { rows: data.headlines || DEMO.headlines });
      case "wire-board": return h(WireBoard, { wires: data.wires || DEMO.wires, catalysts: data.catalysts || DEMO.catalysts });
      case "predict-board": return h(PredictBoard, { book: data.predictions || DEMO.predictions });
      case "coverage-board": return h(CoverageBoard, { rows: data.coverage || DEMO.coverage, jobs: data.jobs || DEMO.jobs });
      case "sentiment-dial": return h(Dial, { sentiment: data.sentiment || DEMO.sentiment });
      case "theme-stage": return h(Stage, { themes: data.themes || DEMO.themes, industries: data.industries || DEMO.industries });
      case "reason-check": return h(Reasons, { rows: data.reasons || DEMO.reasons });
      case "money-flow": return h(Money, { money: data.money || DEMO.money });
      case "limit-cards": return h(Limits, { cards: data.limitCards || DEMO.limitCards });
      case "next-candidates": return h(Candidates, { candidates: data.candidates || DEMO.candidates });
      case "fulfillment": return h(Fulfillment, { book: data.fulfillment || DEMO.fulfillment });
      case "tomorrow-line": return h(Tomorrow, { line: data.tomorrow || DEMO.tomorrow });
      default: return h("p", { className: "gs-empty" }, "这块看板还没有画面");
    }
  }

  function Messages(props) {
    const [open, setOpen] = useState("");
    const cards = (props.data && props.data.cards) || DEMO.cards;
    const rail = (props.data && props.data.rail) || DEMO.rail;
    return h("div", { className: "gs-messages" },
      h("ol", { className: "gs-rail" }, rail.map((node) => h("li", { key: node.hour },
        h("span", { className: "gs-icon" }, String(node.count)),
        h("small", null, node.hour)
      ))),
      h("div", { className: "gs-cards" }, cards.map((card) => h("article", {
        key: card.theme,
        className: open === card.theme ? "is-open" : "",
        onClick: () => setOpen(open === card.theme ? "" : card.theme)
      },
        h("header", null, h("strong", null, card.theme), h("em", null, String(card.count))),
        h("p", null, card.summary || "没有摘要"),
        open === card.theme ? h("ul", null, (card.items || []).filter((item) => !item.folded).slice(0, 8).map((item) => h("li", { key: item.id },
          h("time", null, item.time),
          h("span", null, item.title || item.content)
        ))) : null
      )))
    );
  }

  function Overnight(props) {
    const quotes = (props.data && props.data.quotes) || DEMO.quotes;
    const max = Math.max(...quotes.map((quote) => Math.abs(quote.pct)), 1);
    return h("ul", { className: "gs-bars" }, quotes.map((quote) => h("li", { key: quote.code },
      h("span", null, quote.name),
      h("i", { className: quote.pct >= 0 ? "up" : "down", style: { width: Math.max(12, Math.abs(quote.pct) / max * 100) + "%" } }),
      h("b", { className: quote.pct >= 0 ? "up" : "down" }, signed(quote.pct))
    )));
  }

  function Radar(props) {
    const [keyword, setKeyword] = useState("");
    const events = props.events.filter((item) => (item.stockName + item.content + item.status).includes(keyword));
    return h("div", { className: "gs-feed" },
      h("input", { value: keyword, placeholder: "搜索雷达", onChange: (event) => setKeyword(event.target.value) }),
      events.map((item, index) => h("article", { key: item.id || index, className: index ? "" : "is-fresh" },
        h("header", null, h("strong", null, item.stockName || "未命名"), h("time", null, item.time)),
        h("div", { className: "gs-chips" }, [item.lbStatus, item.status].filter(Boolean).map((chip) => h("em", { key: chip }, chip))),
        h("p", null, highlight(item.content))
      ))
    );
  }

  function Dynamics(props) {
    const [keyword, setKeyword] = useState("");
    const items = props.items.filter((item) => (item.comment + item.stock).includes(keyword));
    return h("div", { className: "gs-feed" },
      h("input", { value: keyword, placeholder: "搜索动态", onChange: (event) => setKeyword(event.target.value) }),
      h("ol", { className: "gs-pulse" }, items.map((item, index) => h("li", { key: item.id || index, className: index ? "" : "is-fresh" },
        h("time", null, item.time),
        item.stock ? h("em", null, item.stock) : h("span"),
        h("p", null, highlight(item.comment))
      )))
    );
  }

  function Dial(props) {
    const row = props.sentiment || DEMO.sentiment;
    const cells = [
      ["涨停", row.limitUp],
      ["炸板", row.broken],
      ["最高连板", row.maxBoard],
      ["跌停", row.limitDown],
      ["打板成功率", row.sealRate == null ? "—" : row.sealRate + "%"],
      ["打板溢价", row.premium == null ? "—" : row.premium + "%"]
    ];
    return h("div", { className: "gs-dial" }, cells.map((cell) => h("div", { key: cell[0] },
      h("b", null, cell[1] == null ? "—" : String(cell[1])),
      h("span", null, cell[0])
    )));
  }

  function Stage(props) {
    const themes = props.themes || DEMO.themes;
    const industries = props.industries || DEMO.industries;
    return h("div", { className: "gs-stage" },
      STAGES.map((stage) => h("section", { key: stage },
        h("h3", null, stage),
        h("div", null, themes.filter((theme) => theme.stage === stage).map((theme) => h("em", {
          key: theme.name,
          className: theme.verdict === "口袋" ? "is-pocket" : ""
        }, theme.name + " " + theme.height + "板")))
      )),
      h("section", { className: "gs-industry" },
        h("h3", null, "行业"),
        h("div", null, industries.map((item) => h("em", { key: item.name }, item.name + " " + item.count)))
      )
    );
  }

  function Reasons(props) {
    const rows = props.rows || DEMO.reasons;
    return h("div", { className: "gs-reasons" }, rows.map((row) => h("article", { key: row.name },
      h("header", null, h("strong", null, row.name), h("em", { className: row.verdict === "成立" ? "up" : "" }, row.verdict)),
      h("p", null, row.line || "没有")
    )));
  }

  function Money(props) {
    const money = props.money || DEMO.money;
    return h("div", { className: "gs-money" },
      h(BarList, { title: "净流入", rows: money.inflow, kind: "up" }),
      h(BarList, { title: "净流出", rows: money.outflow, kind: "down" })
    );
  }

  function BarList(props) {
    const max = Math.max(...props.rows.map((row) => Math.abs(row.yi || 0)), 1);
    return h("div", null,
      h("h3", null, props.title),
      props.rows.map((row) => h("p", { key: row.name },
        h("span", null, row.name),
        h("i", { className: props.kind, style: { width: Math.max(10, Math.abs(row.yi) / max * 100) + "%" } }),
        h("b", null, String(row.yi))
      ))
    );
  }

  function Limits(props) {
    const cards = props.cards || DEMO.limitCards;
    const rows = (cards.up || []).concat(cards.down || []);
    return h("div", { className: "gs-limits" }, rows.slice(0, 18).map((card) => h("article", { key: card.side + card.code, className: card.side },
      h("header", null, h("strong", null, card.name), h("em", null, card.push)),
      h("p", null, (card.theme || "") + " · " + (card.side === "up" ? card.height + "板 · " : "") + (card.line || "没有"))
    )));
  }

  function Candidates(props) {
    const book = props.candidates || DEMO.candidates;
    return h("div", { className: "gs-lanes" },
      h(Lane, { title: "首板候选", groups: book.first }),
      h(Lane, { title: "二板候选", groups: book.second })
    );
  }

  function Lane(props) {
    return h("section", null,
      h("h3", null, props.title),
      (props.groups || []).map((group) => h("div", { key: group.theme, className: "gs-lane-group" },
        h("strong", null, group.theme),
        (group.people || []).map((person) => h("em", { key: person.code }, person.name + " " + (person.prob == null ? "" : person.prob + "%")))
      ))
    );
  }

  function Fulfillment(props) {
    const book = props.book || DEMO.fulfillment;
    return h("div", { className: "gs-fulfill" },
      book.shown.map((item) => h("article", { key: item.name + item.prob },
        h("header", null, h("strong", null, item.name), h("em", { className: item.result === "hit" ? "up" : "down" }, item.result === "hit" ? "中" : "未中")),
        h("div", { className: "gs-mini" }, (item.bars || []).map((bar, index) => h("i", {
          key: index,
          className: bar >= 0 ? "up" : "down",
          style: { height: Math.max(6, Math.min(28, Math.abs(bar || 0) * 3)) + "px" }
        })))
      )),
      book.quietMisses ? h("p", { className: "gs-quiet" }, "低概率未中 " + book.quietMisses) : null
    );
  }

  function Tomorrow(props) {
    const line = props.line || DEMO.tomorrow;
    return h("div", { className: "gs-tomorrow" },
      h("b", null, line.status || "中性"),
      h("div", null, (line.chips || []).slice(0, 3).map((chip) => h("em", { key: chip }, chip)))
    );
  }

  function IndexBoard(props) {
    return h("ul", { className: "gs-bars" }, (props.rows || []).map((row) => h("li", { key: row.code },
      h("span", null, row.name),
      h("i", { className: (row.pct || 0) >= 0 ? "up" : "down", style: { width: Math.max(12, Math.abs(row.pct || 0) * 18) + "%" } }),
      h("b", { className: (row.pct || 0) >= 0 ? "up" : "down" }, row.close == null ? "—" : row.close + " " + signed(row.pct || 0))
    )));
  }

  function BreadthBoard(props) {
    const breadth = props.breadth || DEMO.breadth;
    const buckets = breadth.buckets || [];
    const max = Math.max(...buckets.map((row) => row.count || 0), 1);
    return h("div", null,
      h("div", { className: "gs-dial" }, [
        ["上涨", breadth.up],
        ["下跌", breadth.down],
        ["平盘", breadth.flat]
      ].map((cell) => h("div", { key: cell[0] }, h("b", null, String(cell[1] == null ? "—" : cell[1])), h("span", null, cell[0])))),
      h("ul", { className: "gs-bars" }, buckets.map((row) => h("li", { key: row.label },
        h("span", null, row.label),
        h("i", { className: "up", style: { width: Math.max(8, row.count / max * 100) + "%" } }),
        h("b", null, String(row.count))
      )))
    );
  }

  function MinuteBoard(props) {
    return h("div", { className: "gs-sparks" }, (props.rows || []).map((row) => {
      const points = row.points || [];
      const low = Math.min(...points);
      const high = Math.max(...points);
      const span = Math.max(high - low, 0.01);
      return h("section", { key: row.code },
        h("h3", null, row.name),
        h("div", { className: "gs-spark" }, points.map((point, index) => h("i", {
          key: index,
          style: { height: Math.max(8, (point - low) / span * 64) + "px" }
        })))
      );
    }));
  }

  function HourBoard(props) {
    const rows = props.rows || [];
    if (!rows.length) return h("p", { className: "gs-empty" }, "还没有小时成交");
    return h("table", { className: "gs-table" },
      h("thead", null, h("tr", null, ["时间", "上证额", "深成额", "创业板额"].map((label) => h("th", { key: label }, label)))),
      h("tbody", null, rows.map((row) => h("tr", { key: row.slot },
        h("td", null, row.slot),
        h("td", null, row.shAmount == null ? "—" : String(row.shAmount)),
        h("td", null, row.szAmount == null ? "—" : String(row.szAmount)),
        h("td", null, row.cyAmount == null ? "—" : String(row.cyAmount))
      )))
    );
  }

  function SectorBoard(props) {
    const sectors = props.sectors || DEMO.sectors;
    return h("div", { className: "gs-lanes" },
      h(BarList, { title: "涨幅", rows: (sectors.gainers || []).map((row) => ({ name: row.name, yi: row.pct })), kind: "up" }),
      h(BarList, { title: "跌幅", rows: (sectors.losers || []).map((row) => ({ name: row.name, yi: row.pct })), kind: "down" }),
      h(BarList, { title: "净流入（亿）", rows: sectors.inflow || [], kind: "up" })
    );
  }

  function LeaderBoard(props) {
    const leaders = props.leaders || DEMO.leaders;
    const line = (row) => h("p", { key: row.code },
      h("span", null, row.name),
      h("b", { className: (row.pct || 0) >= 0 ? "up" : "down" }, signed(row.pct || 0))
    );
    return h("div", { className: "gs-lanes" },
      h("div", null, h("h3", null, "领涨"), (leaders.up || []).map(line)),
      h("div", null, h("h3", null, "领跌"), (leaders.down || []).map(line))
    );
  }

  function AuctionBoard(props) {
    return h("ul", { className: "gs-bars" }, (props.rows || []).map((row) => h("li", { key: row.code },
      h("span", null, row.name),
      h("i", { className: (row.pct || 0) >= 0 ? "up" : "down", style: { width: Math.max(8, Math.abs(row.pct || 0) * 8) + "%" } }),
      h("b", { className: (row.pct || 0) >= 0 ? "up" : "down" }, signed(row.pct || 0))
    )));
  }

  function LineList(props) {
    return h("ol", { className: "gs-pulse" }, (props.rows || []).map((row, index) => h("li", { key: index },
      h("time", null, row.time || row.date || ""),
      h("em", null, row.source || row.level || ""),
      h("p", null, row.title || row.summary || "")
    )));
  }

  function WireBoard(props) {
    return h("div", null,
      h(LineList, { rows: props.wires || [] }),
      h("h3", null, "催化"),
      h(LineList, { rows: (props.catalysts || []).map((row) => ({ time: row.date, source: row.level, title: row.summary })) })
    );
  }

  function PredictBoard(props) {
    const book = props.book || DEMO.predictions;
    return h("div", null,
      h("div", { className: "gs-chips" }, (book.results || []).map((row) => h("em", { key: row.result }, row.result + " " + row.count))),
      h(LineList, { rows: (book.recent || []).map((row) => ({ time: row.result, source: row.category, title: row.statement })) })
    );
  }

  function CoverageBoard(props) {
    return h("div", { className: "gs-lanes" },
      h("table", { className: "gs-table" },
        h("tbody", null, (props.rows || []).map((row) => h("tr", { key: row.name },
          h("td", null, row.name),
          h("td", null, String(row.rows)),
          h("td", null, row.latest || "—")
        )))
      ),
      h("table", { className: "gs-table" },
        h("tbody", null, (props.jobs || []).map((row) => h("tr", { key: row.job + row.status },
          h("td", null, row.job),
          h("td", null, row.status),
          h("td", null, row.last || "")
        )))
      )
    );
  }

  function highlight(text) {
    const parts = String(text || "").split(/(减少|\d+(?:\.\d+)?%?)/g);
    return parts.map((part, index) => {
      if (part === "减少") return h("mark", { key: index, className: "down" }, part);
      if (/^\d+(?:\.\d+)?%?$/.test(part)) return h("mark", { key: index }, part);
      return h("span", { key: index }, part);
    });
  }

  function signed(value) {
    const number = Number(value);
    return (number > 0 ? "+" : "") + number.toFixed(2) + "%";
  }

  function Style() {
    return h("style", null, CSS);
  }

  function NavIcon() {
    return h("span", { className: "gs-nav-icon", "aria-hidden": "true" }, "观");
  }

  const CSS = `
.gs{--gs-bg:#F8FAFC;--gs-card:#FFFFFF;--gs-soft:#F1F5F9;--gs-ink:#1F2937;--gs-muted:#6B7280;--gs-faint:#9CA3AF;--gs-primary:#6366F1;--gs-primary-strong:#4F46E5;--gs-up:#EF4444;--gs-down:#10B981;--gs-shadow:0 20px 40px rgba(148,163,184,.28);--gs-shadow-hover:0 24px 48px rgba(99,102,241,.18);height:100%;min-height:100%;overflow:auto;background:var(--gs-bg);color:var(--gs-ink);font-family:"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.55;position:relative}
.gs[data-scheme="dark"]{--gs-bg:#0F172A;--gs-card:#1E293B;--gs-soft:#334155;--gs-ink:#F8FAFC;--gs-muted:#CBD5E1;--gs-faint:#94A3B8;--gs-primary:#818CF8;--gs-primary-strong:#6366F1;--gs-up:#F87171;--gs-down:#34D399;--gs-shadow:0 20px 40px rgba(2,6,23,.35);--gs-shadow-hover:0 24px 48px rgba(99,102,241,.22)}
.gs button,.gs input{font:inherit}
.gs button{cursor:pointer;min-height:44px;transition:all .2s ease-in-out}
.gs button:active{transform:scale(.95)}
.gs button:focus-visible,.gs input:focus-visible{outline:none;box-shadow:0 0 0 4px rgba(99,102,241,.35)}
.gs-top{display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:24px 24px 8px;position:sticky;top:0;z-index:5;background:color-mix(in srgb, var(--gs-bg) 92%, transparent);backdrop-filter:blur(18px)}
.gs-brand{display:flex;flex-direction:column;min-width:88px;gap:4px}
.gs-brand strong{font-size:28px;font-weight:600;letter-spacing:-0.03em;color:var(--gs-ink)}
.gs-brand span{color:var(--gs-faint);font-size:12px}
.gs-tabs,.gs-scheme{display:flex;gap:8px;padding:6px;background:var(--gs-card);border-radius:24px;box-shadow:var(--gs-shadow)}
.gs-tabs button,.gs-scheme button,.gs-menu button{border:0;background:transparent;color:var(--gs-muted);border-radius:16px;padding:0 18px;font-weight:500}
.gs-tabs button:hover,.gs-scheme button:hover,.gs-menu button:hover{color:var(--gs-ink);transform:translateY(-2px);box-shadow:var(--gs-shadow-hover)}
.gs-tabs button.is-on,.gs-scheme button.is-on{background:var(--gs-primary-strong);color:#FFFFFF;box-shadow:0 12px 28px rgba(79,70,229,.30)}
.gs-date{background:var(--gs-soft);color:inherit;border:0;border-radius:16px;padding:10px 16px;min-height:44px;box-shadow:none;transition:all .2s ease-in-out}
.gs-date:focus{background:var(--gs-card);box-shadow:0 0 0 4px rgba(99,102,241,.35)}
.gs-risk{margin:8px 24px 8px;color:var(--gs-muted);font-size:13px;max-width:42rem}
.gs-gap{margin:0 24px 8px;color:var(--gs-primary-strong);font-size:13px}
.gs-canvas{position:relative;margin:8px 16px 32px}
.gs-canvas.is-narrow{display:flex;flex-direction:column;gap:24px}
.gs-frame{position:absolute;background:var(--gs-card);border:0;border-radius:24px;display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--gs-shadow);transition:all .3s ease-in-out}
.gs-frame:hover{transform:translateY(-2px);box-shadow:var(--gs-shadow-hover)}
.gs-canvas.is-narrow .gs-frame{position:relative;left:auto;top:auto;width:auto;height:auto;min-height:240px}
.gs-frame-title{display:flex;justify-content:space-between;align-items:center;padding:20px 24px 8px;cursor:grab}
.gs-frame-label{display:flex;align-items:center;gap:10px}
.gs-frame-label strong{font-size:18px;font-weight:600;color:var(--gs-ink)}
.gs-dot{width:28px;height:28px;border-radius:999px;background:rgba(99,102,241,.12);box-shadow:inset 0 0 0 6px rgba(99,102,241,.18)}
.gs-frame-title button{width:36px;min-height:36px;border:0;border-radius:999px;background:rgba(99,102,241,.10);color:var(--gs-primary-strong);padding:0}
.gs-frame-title button:hover{transform:translateY(-2px);box-shadow:var(--gs-shadow-hover);background:var(--gs-primary-strong);color:#FFFFFF}
.gs-frame-body{padding:8px 24px 24px;overflow:auto;min-height:0;flex:1}
.gs-handle{position:absolute}
.gs-handle-e,.gs-handle-w{top:36px;bottom:24px;width:12px;cursor:ew-resize}
.gs-handle-e{right:0}.gs-handle-w{left:0}
.gs-handle-n,.gs-handle-s{left:36px;right:24px;height:12px;cursor:ns-resize}
.gs-handle-n{top:0}.gs-handle-s{bottom:0}
.gs-handle-se{right:10px;bottom:10px;width:16px;height:16px;cursor:nwse-resize;border-radius:999px;background:rgba(99,102,241,.18)}
.gs-menu{position:fixed;z-index:20;background:var(--gs-card);border:0;border-radius:24px;padding:12px;display:flex;flex-direction:column;gap:6px;min-width:200px;max-height:70vh;overflow:auto;box-shadow:var(--gs-shadow)}
.gs-table{width:100%;border-collapse:collapse;font-size:13px}
.gs-table th,.gs-table td{padding:8px 6px;text-align:left;color:var(--gs-ink)}
.gs-table tbody tr+tr td{border-top:1px solid rgba(148,163,184,.25)}
.gs-sparks{display:flex;flex-direction:column;gap:16px}
.gs-spark{display:flex;align-items:flex-end;gap:3px;height:72px}
.gs-spark i{flex:1;border-radius:999px;background:rgba(99,102,241,.55);min-width:4px}
.gs-menu p{margin:6px 10px;font-size:12px;color:var(--gs-faint)}
.gs-menu button{text-align:left;padding:0 14px;color:var(--gs-ink);background:transparent;border-radius:16px}
.gs-menu button.is-danger{color:var(--gs-up)}
.gs-empty,.gs-quiet{color:var(--gs-muted);padding:8px 0}
.gs-dial{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:16px}
.gs-dial div{background:var(--gs-soft);border-radius:20px;padding:16px;box-shadow:0 10px 24px rgba(148,163,184,.18)}
.gs-dial b{display:block;font-size:30px;line-height:1.1;font-weight:600;letter-spacing:-0.03em;color:var(--gs-ink)}
.gs-dial span{color:var(--gs-muted);font-size:12px}
.gs-stage{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.gs-stage h3,.gs-money h3,.gs-lanes h3{margin:0 0 10px;font-size:13px;font-weight:600;color:var(--gs-muted)}
.gs-stage em,.gs-chips em,.gs-lanes em,.gs-tomorrow em,.gs-pulse em{display:inline-flex;align-items:center;margin:0 8px 8px 0;padding:6px 12px;background:rgba(99,102,241,.10);color:var(--gs-primary-strong);border-radius:999px;font-style:normal;font-size:13px;font-weight:500}
.gs-stage em.is-pocket{opacity:.55}
.gs-messages{display:grid;grid-template-columns:96px 1fr;gap:24px;height:100%}
.gs-rail{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:16px}
.gs-icon{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;padding:0 10px;border-radius:999px;background:rgba(99,102,241,.12);color:var(--gs-primary-strong);font-weight:600}
.gs-rail small{display:block;margin-top:6px;color:var(--gs-faint)}
.gs-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;align-content:start}
.gs-cards article,.gs-feed article,.gs-reasons article,.gs-limits article,.gs-fulfill article,.gs-lane-group{background:var(--gs-soft);padding:20px;border-radius:24px;box-shadow:0 12px 28px rgba(148,163,184,.16);transition:all .3s ease-in-out}
.gs-cards article:hover,.gs-feed article:hover,.gs-reasons article:hover,.gs-limits article:hover,.gs-fulfill article:hover{transform:translateY(-2px);box-shadow:var(--gs-shadow-hover)}
.gs-cards header,.gs-feed header,.gs-reasons header,.gs-limits header,.gs-fulfill header{display:flex;justify-content:space-between;gap:10px;align-items:center}
.gs-cards p,.gs-feed p,.gs-reasons p,.gs-limits p,.gs-pulse p{margin:8px 0 0;color:var(--gs-muted);font-size:14px}
.gs-cards ul{margin:12px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px}
.gs-cards li{display:flex;gap:10px;color:var(--gs-ink);font-size:13px}
.gs-feed{display:flex;flex-direction:column;gap:16px}
.gs-feed input{background:var(--gs-soft);color:inherit;border:0;border-radius:16px;padding:12px 16px;min-height:44px;transition:all .2s ease-in-out}
.gs-feed input:focus{background:var(--gs-card);box-shadow:0 0 0 4px rgba(99,102,241,.35)}
.gs-pulse{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
.gs-pulse li{display:grid;grid-template-columns:72px auto 1fr;gap:12px;align-items:start;padding:12px 0}
.gs-pulse time,.gs-feed time{color:var(--gs-faint);font-size:12px}
.gs-pulse .is-fresh,.gs-feed .is-fresh{animation:gs-in .25s ease-in-out}
.up{color:var(--gs-up)} .down{color:var(--gs-down)}
.gs-bars,.gs-money p{display:grid;grid-template-columns:96px 1fr 64px;gap:12px;align-items:center;margin:10px 0}
.gs-bars{list-style:none;padding:0;margin:0}
.gs-bars i,.gs-money i{display:block;height:10px;border-radius:999px}
.gs-bars i.up,.gs-money i.up{background:rgba(239,68,68,.75)}
.gs-bars i.down,.gs-money i.down{background:rgba(16,185,129,.75)}
.gs-reasons,.gs-limits,.gs-fulfill{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}
.gs-lanes{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.gs-lane-group{margin-bottom:12px}
.gs-mini{display:flex;align-items:flex-end;gap:4px;height:36px;margin-top:12px}
.gs-mini i{display:block;width:8px;border-radius:999px}
.gs-mini i.up{background:rgba(239,68,68,.75)} .gs-mini i.down{background:rgba(16,185,129,.75)}
.gs-tomorrow b{display:block;font-size:40px;line-height:1;font-weight:600;letter-spacing:-0.04em;margin-bottom:16px;color:var(--gs-ink)}
.gs-nav-icon{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:rgba(99,102,241,.12);color:var(--gs-primary-strong);font-weight:600}
mark{background:transparent;color:var(--gs-primary-strong);font-weight:600}
mark.down{color:var(--gs-down)}
@keyframes gs-in{from{transform:translateY(-6px);opacity:0}to{transform:none;opacity:1}}
@media (prefers-reduced-motion: reduce){
  .gs button,.gs-frame,.gs-cards article,.gs-feed article,.gs-reasons article,.gs-limits article,.gs-fulfill article,.gs-pulse .is-fresh,.gs-feed .is-fresh{transition:none;animation:none;transform:none}
}
@media (max-width:840px){
  .gs-top{padding:16px}
  .gs-brand strong{font-size:24px}
  .gs-dial{grid-template-columns:repeat(2,minmax(0,1fr))}
  .gs-messages,.gs-lanes,.gs-pulse li,.gs-stage{grid-template-columns:1fr}
  .gs-frame-body{padding:8px 20px 20px}
}
`;

  module.exports.name = "guanshi-board-client";
  module.exports.inject = ["slots", "layout", "theme"];
  module.exports.apply = function (ctx) {
    ctx.slots.inject("main", () => ctx.slots.register({
      name: "main",
      key: "guanshi-board",
      inject: () => ({
        setScheme: function (id) {
          try { ctx.theme.setTheme(id); } catch (error) {}
        }
      })
    }, BoardPanel));
    ctx.slots.inject("sidebar.panellist", () => ctx.slots.register({
      name: "sidebar.panellist",
      id: "guanshi-board",
      label: "观势",
      order: 8
    }, NavIcon));
  };
  return module.exports;
}});
