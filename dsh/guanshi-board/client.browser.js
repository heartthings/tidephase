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
  const PLACE = {
    "preopen-messages": { span: 8, min: 420 },
    "overnight": { span: 4, min: 260 },
    "index-board": { span: 12, min: 108 },
    "breadth-board": { span: 5, min: 260 },
    "sentiment-dial": { span: 7, min: 132 },
    "minute-board": { span: 8, min: 240 },
    "hour-board": { span: 4, min: 240 },
    "sector-board": { span: 7, min: 280 },
    "leader-board": { span: 5, min: 280 },
    "auction-board": { span: 4, min: 240 },
    "news-board": { span: 4, min: 240 },
    "market-radar": { span: 6, min: 300 },
    "market-dynamics": { span: 6, min: 300 },
    "wire-board": { span: 6, min: 220 },
    "predict-board": { span: 6, min: 220 },
    "coverage-board": { span: 12, min: 200 },
    "theme-stage": { span: 8, min: 300 },
    "tomorrow-line": { span: 4, min: 160 },
    "money-flow": { span: 12, min: 200 },
    "reason-check": { span: 6, min: 260 },
    "limit-cards": { span: 6, min: 260 },
    "next-candidates": { span: 8, min: 280 },
    "fulfillment": { span: 4, min: 260 }
  };

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
    const [session, setSession] = useState(sessionForNow);
    const [date, setDate] = useState(todayISO());
    const [spec, setSpec] = useState(DEFAULT_SPEC);
    const [picker, setPicker] = useState(false);
    const [narrow, setNarrow] = useState(window.innerWidth < 840);
    const [scheme, setScheme] = useState(initialScheme);
    const [payload, setPayload] = useState(DEMO);
    const [gaps, setGaps] = useState([]);
    const [usingDemo, setUsingDemo] = useState(true);
    const [updatedAt, setUpdatedAt] = useState("");
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
        readJSON("/api/public/v1/boards/spec").then((body) => {
          if (stop || !body || !body.data) return;
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
          setUpdatedAt(clockNow());
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

    const boards = orderedBoards(session, (spec.sessions[session] && spec.sessions[session].boards) || []);
    const shown = new Set(boards.map((board) => board.type));
    const notes = gaps.filter((gap) => gap !== "当前使用示例数据");

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

    function writeBoards(nextBoards) {
      commit({
        ...spec,
        sessions: {
          ...spec.sessions,
          [session]: { boards: nextBoards }
        }
      });
    }

    function toggleType(type) {
      if (shown.has(type)) {
        writeBoards(boards.filter((board) => board.type !== type));
        return;
      }
      writeBoards(boards.concat({
        id: type + "-" + Date.now().toString(36),
        type: type,
        x: 16,
        y: 16,
        w: 480,
        h: 280
      }));
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
          h("span", null, "A股")
        ),
        h("nav", { className: "gs-tabs", "aria-label": "时段" }, SESSIONS.map((item) => h("button", {
          key: item.id,
          type: "button",
          className: session === item.id ? "is-on" : "",
          "aria-pressed": session === item.id,
          onClick: () => { setSession(item.id); setPicker(false); }
        }, item.label))),
        h("input", {
          className: "gs-date",
          type: "date",
          "aria-label": "交易日",
          value: date,
          onChange: (event) => setDate(event.target.value)
        }),
        h("div", { className: "gs-scheme", "aria-label": "配色" }, ["light", "dark"].map((item) => h("button", {
          key: item,
          type: "button",
          className: scheme === item ? "is-on" : "",
          "aria-pressed": scheme === item,
          onClick: () => switchScheme(item)
        }, item === "light" ? "浅色" : "深色"))),
        h("div", { className: "gs-picker" },
          h("button", {
            type: "button",
            className: picker ? "is-on" : "",
            "aria-expanded": picker,
            "aria-controls": "gs-panel-menu",
            onClick: () => setPicker(!picker)
          }, "面板"),
          picker ? h("div", {
            id: "gs-panel-menu",
            className: "gs-menu",
            role: "group",
            "aria-label": "选择看板"
          },
            h("p", null, "当前时段显示这些看板"),
            CATALOG[session].map((item) => h("button", {
              key: item.type,
              type: "button",
              className: shown.has(item.type) ? "is-on" : "",
              "aria-pressed": shown.has(item.type),
              onClick: () => toggleType(item.type)
            },
              h("i", { "aria-hidden": "true" }, shown.has(item.type) ? "✓" : ""),
              item.title
            ))
          ) : null
        ),
        h("p", { className: "gs-status" },
          h("b", { className: usingDemo ? "is-demo" : "is-live" }, usingDemo ? "示例" : "实时"),
          h("span", null, updatedAt ? "刷新 " + updatedAt : "等待接口"),
          h("span", null, "数据会延迟，不是投资建议")
        )
      ),
      notes.length ? h("details", { className: "gs-gap" },
        h("summary", null, "数据缺口 " + notes.length + " 条"),
        notes.map((gap) => h("p", { key: gap }, gap))
      ) : null,
      picker ? h("button", {
        type: "button",
        className: "gs-scrim",
        "aria-label": "关闭面板列表",
        onClick: () => setPicker(false)
      }) : null,
      h("div", { className: narrow ? "gs-canvas is-narrow" : "gs-canvas" }, boards.map((board) => {
        const place = placeOf(session, board.type, boards.length);
        return h(Frame, {
          key: board.id,
          board: board,
          narrow: narrow,
          span: place.span,
          minHeight: place.min,
          payload: payload
        });
      }))
    );
  }

  function initialScheme() {
    if (document.body && document.body.hasAttribute("data-ds-dark-theme")) return "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function sessionForNow() {
    const now = new Date();
    const day = now.getDay();
    if (day === 0 || day === 6) return "afterclose";
    const hour = now.getHours();
    if (hour < 9) return "preopen";
    if (hour < 15) return "intraday";
    return "afterclose";
  }

  function clockNow() {
    return new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function orderedBoards(session, boards) {
    const order = {
      preopen: ["preopen-messages", "overnight"],
      intraday: ["index-board", "breadth-board", "sentiment-dial", "minute-board", "hour-board", "sector-board", "leader-board", "auction-board", "overnight", "news-board", "market-radar", "market-dynamics", "wire-board", "predict-board", "coverage-board"],
      afterclose: ["sentiment-dial", "theme-stage", "tomorrow-line", "reason-check", "limit-cards", "money-flow", "next-candidates", "fulfillment"]
    };
    const rank = new Map((order[session] || []).map((type, index) => [type, index]));
    return boards.slice().sort((a, b) => (rank.get(a.type) == null ? 99 : rank.get(a.type)) - (rank.get(b.type) == null ? 99 : rank.get(b.type)));
  }

  function placeOf(session, type, count) {
    if (count <= 1) return { span: 12, min: 320 };
    if (session === "afterclose" && type === "sentiment-dial") return { span: 12, min: 120 };
    return PLACE[type] || { span: 6, min: 220 };
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
    const style = props.narrow
      ? { minHeight: props.minHeight }
      : { gridColumn: "span " + props.span, minHeight: props.minHeight };
    return h("section", { className: "gs-frame", style: style },
      h("header", { className: "gs-frame-title" },
        h("strong", null, TITLES[board.type] || board.type)
      ),
      h("div", { className: "gs-frame-body" }, h(Body, { type: board.type, payload: props.payload }))
    );
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
    return h("ul", { className: "gs-bars" }, quotes.map((quote) => h("li", { key: quote.code, className: "gs-bar-row" },
      h("span", null, quote.name),
      h("span", { className: "gs-bar-track" },
        h("i", { className: quote.pct >= 0 ? "up" : "down", style: { width: Math.max(4, Math.abs(quote.pct) / max * 100) + "%" } })
      ),
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
    return h("div", { className: "gs-dial" }, cells.map((cell) => h("div", { key: cell[0], className: dialTone(cell[0], cell[1]) },
      h("span", null, cell[0]),
      h("b", null, cell[1] == null ? "—" : String(cell[1]))
    )));
  }

  function Stage(props) {
    const themes = props.themes || DEMO.themes;
    const industries = props.industries || DEMO.industries;
    return h("div", { className: "gs-stage" },
      STAGES.map((stage) => h("section", { key: stage },
        h("h3", null, stage),
        h("div", null, themes.some((theme) => theme.stage === stage) ? themes.filter((theme) => theme.stage === stage).map((theme) => h("em", {
          key: theme.name,
          className: theme.verdict === "口袋" ? "is-pocket" : ""
        }, theme.name + " " + theme.height + "板")) : h("span", { className: "gs-empty" }, "无"))
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
      props.rows.map((row) => h("p", { key: row.name, className: "gs-bar-row" },
        h("span", null, row.name),
        h("span", { className: "gs-bar-track" },
          h("i", { className: props.kind, style: { width: Math.max(4, Math.abs(row.yi) / max * 100) + "%" } })
        ),
        h("b", { className: props.kind }, amountText(row.yi))
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
      h(Lane, { title: "一板候选", groups: book.first })
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
    return h("div", { className: "gs-stats" }, (props.rows || []).map((row) => h("div", {
      key: row.code,
      className: (row.pct || 0) >= 0 ? "up" : "down"
    },
      h("span", null, row.name),
      h("b", null, signed(row.pct || 0)),
      h("small", null, row.close == null ? "—" : formatNumber(row.close))
    )));
  }

  function BreadthBoard(props) {
    const breadth = props.breadth || DEMO.breadth;
    const buckets = breadth.buckets || [];
    const max = Math.max(...buckets.map((row) => row.count || 0), 1);
    return h("div", { className: "gs-breadth" },
      h("div", { className: "gs-stats gs-stats-3" }, [
        ["上涨", breadth.up, "up"],
        ["下跌", breadth.down, "down"],
        ["平盘", breadth.flat, ""]
      ].map((cell) => h("div", { key: cell[0], className: cell[2] },
        h("span", null, cell[0]),
        h("b", null, String(cell[1] == null ? "—" : cell[1]))
      ))),
      h("div", { className: "gs-hist", role: "img", "aria-label": "涨跌家数分布" }, buckets.map((row) => h("div", { key: row.label, className: "gs-hist-col" },
        h("b", null, String(row.count)),
        h("i", { className: bucketTone(row.label), style: { height: Math.max(4, (row.count || 0) / max * 72) + "px" } }),
        h("span", null, row.label)
      )))
    );
  }

  function MinuteBoard(props) {
    return h("div", { className: "gs-sparks" }, (props.rows || []).map((row) => h(SeriesLine, { key: row.code, row: row })));
  }

  function SeriesLine(props) {
    const row = props.row;
    const points = row.points || [];
    if (points.length < 2) return h("p", { className: "gs-empty" }, (row.name || "指数") + "还没有分钟");
    const width = 360;
    const height = 96;
    const pad = 6;
    const low = Math.min.apply(null, points);
    const high = Math.max.apply(null, points);
    const span = Math.max(high - low, 0.01);
    const coords = points.map((point, index) => {
      const x = pad + index / (points.length - 1) * (width - pad * 2);
      const y = pad + (1 - (point - low) / span) * (height - pad * 2);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    const first = points[0];
    const last = points[points.length - 1];
    const change = first ? (last - first) / first * 100 : 0;
    const tone = change >= 0 ? "up" : "down";
    const baseY = pad + (1 - (first - low) / span) * (height - pad * 2);
    return h("section", null,
      h("header", { className: "gs-series-head" },
        h("h3", null, row.name),
        h("b", { className: tone }, formatNumber(last) + "  " + signed(change))
      ),
      h("svg", {
        className: "gs-line",
        viewBox: "0 0 " + width + " " + height,
        role: "img",
        "aria-label": row.name + " " + signed(change)
      },
        h("line", { x1: pad, x2: width - pad, y1: baseY, y2: baseY }),
        h("polyline", { className: tone, points: coords })
      )
    );
  }

  function HourBoard(props) {
    const rows = props.rows || [];
    if (!rows.length) return h("p", { className: "gs-empty" }, "还没有小时成交");
    return h("table", { className: "gs-table" },
      h("thead", null, h("tr", null, ["时间", "上证额", "深成额", "创业板额"].map((label, index) => h("th", { key: label, className: index ? "num" : "" }, label)))),
      h("tbody", null, rows.map((row) => h("tr", { key: row.slot },
        h("td", null, row.slot),
        h("td", { className: "num" }, row.shAmount == null ? "—" : formatNumber(row.shAmount)),
        h("td", { className: "num" }, row.szAmount == null ? "—" : formatNumber(row.szAmount)),
        h("td", { className: "num" }, row.cyAmount == null ? "—" : formatNumber(row.cyAmount))
      )))
    );
  }

  function SectorBoard(props) {
    const sectors = props.sectors || DEMO.sectors;
    return h("div", { className: "gs-lanes gs-lanes-3" },
      h(BarList, { title: "涨幅", rows: (sectors.gainers || []).map((row) => ({ name: row.name, yi: row.pct })), kind: "up" }),
      h(BarList, { title: "跌幅", rows: (sectors.losers || []).map((row) => ({ name: row.name, yi: row.pct })), kind: "down" }),
      h(BarList, { title: "净流入（亿）", rows: sectors.inflow || [], kind: "up" })
    );
  }

  function LeaderBoard(props) {
    const leaders = props.leaders || DEMO.leaders;
    const line = (row) => h("p", { key: row.code, className: "gs-pair" },
      h("span", null, row.name),
      h("b", { className: (row.pct || 0) >= 0 ? "up" : "down" }, signed(row.pct || 0))
    );
    return h("div", { className: "gs-lanes" },
      h("div", null, h("h3", null, "领涨"), (leaders.up || []).map(line)),
      h("div", null, h("h3", null, "领跌"), (leaders.down || []).map(line))
    );
  }

  function AuctionBoard(props) {
    const rows = props.rows || [];
    const max = Math.max.apply(null, rows.map((row) => Math.abs(row.pct || 0)).concat(1));
    return h("ul", { className: "gs-bars" }, rows.map((row) => h("li", { key: row.code, className: "gs-bar-row" },
      h("span", null, row.name),
      h("span", { className: "gs-bar-track" },
        h("i", { className: (row.pct || 0) >= 0 ? "up" : "down", style: { width: Math.max(4, Math.abs(row.pct || 0) / max * 100) + "%" } })
      ),
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
        h("thead", null, h("tr", null, ["表", "行数", "最新"].map((label, index) => h("th", { key: label, className: index === 1 ? "num" : "" }, label)))),
        h("tbody", null, (props.rows || []).map((row) => h("tr", { key: row.name },
          h("td", null, row.name),
          h("td", { className: "num" }, formatNumber(row.rows)),
          h("td", null, row.latest || "—")
        )))
      ),
      h("table", { className: "gs-table" },
        h("thead", null, h("tr", null, ["作业", "状态", "时间"].map((label) => h("th", { key: label }, label)))),
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
    if (!Number.isFinite(number)) return "—";
    return (number > 0 ? "+" : "") + number.toFixed(2) + "%";
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }

  function amountText(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return (number > 0 ? "+" : "") + number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }

  function dialTone(label, value) {
    if (label === "涨停") return "up";
    if (label === "跌停" || label === "炸板") return "down";
    if (label === "打板溢价") {
      const number = Number(String(value).replace("%", ""));
      if (!Number.isFinite(number) || number === 0) return "";
      return number > 0 ? "up" : "down";
    }
    return "";
  }

  function bucketTone(label) {
    const text = String(label || "");
    if (text.includes("跌") || text.includes("弱")) return "down";
    if (text.includes("涨") || text.includes("强")) return "up";
    return "";
  }

  function Style() {
    return h("style", null, CSS);
  }

  function NavIcon() {
    return h("span", { className: "gs-nav-icon", "aria-hidden": "true" }, "观");
  }

  const CSS = `
.gs{--gs-bg:#f4f5f5;--gs-card:#ffffff;--gs-soft:#f7f8f9;--gs-ink:#1a1a1a;--gs-muted:#4d535a;--gs-faint:#5e656d;--gs-line:#e3e4e6;--gs-track:#eceef0;--gs-up:#c4162a;--gs-down:#1a7f37;--gs-warn:#8a4b08;--gs-focus:#1f60c4;--gs-live:#1a7f37;height:100%;min-height:100%;overflow:auto;background:var(--gs-bg);color:var(--gs-ink);font-family:"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.5;position:relative;font-variant-numeric:tabular-nums}
.gs[data-scheme="dark"]{--gs-bg:#111217;--gs-card:#181b1f;--gs-soft:#111217;--gs-ink:#e6e8ea;--gs-muted:#b7bdc4;--gs-faint:#9aa0a6;--gs-line:#2c3235;--gs-track:#2c3235;--gs-up:#ff8fa0;--gs-down:#73bf69;--gs-warn:#ffb357;--gs-focus:#8ab8ff;--gs-live:#73bf69}
.gs button,.gs input{font:inherit;color:inherit}
.gs button{cursor:pointer;min-height:32px;border:1px solid transparent;background:transparent;border-radius:2px}
.gs button:focus-visible,.gs input:focus-visible{outline:2px solid var(--gs-focus);outline-offset:2px}
.gs-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 12px;position:sticky;top:0;z-index:30;background:var(--gs-bg);border-bottom:1px solid var(--gs-line)}
.gs-brand{display:flex;align-items:baseline;gap:8px;min-width:72px}
.gs-brand strong{font-size:15px;font-weight:600;color:var(--gs-ink)}
.gs-brand span{color:var(--gs-muted);font-size:12px}
.gs-tabs,.gs-scheme{display:flex;gap:2px;padding:2px;background:transparent;border:1px solid var(--gs-line);border-radius:2px}
.gs-tabs button,.gs-scheme button,.gs-picker > button{border:1px solid transparent;background:transparent;color:var(--gs-muted);border-radius:2px;padding:0 12px;font-weight:500}
.gs-tabs button:hover,.gs-scheme button:hover,.gs-picker > button:hover,.gs-menu button:hover{color:var(--gs-ink);background:var(--gs-card)}
.gs-tabs button.is-on,.gs-scheme button.is-on,.gs-picker > button.is-on{background:var(--gs-card);color:var(--gs-ink);border-color:var(--gs-line)}
.gs-date{background:var(--gs-card);color:inherit;border:1px solid var(--gs-line);border-radius:2px;padding:4px 8px;min-height:32px}
.gs-picker{position:relative}
.gs-status{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 0 auto;color:var(--gs-muted);font-size:12px}
.gs-status b{font-weight:600;font-style:normal}
.gs-status b.is-live{color:var(--gs-live)}
.gs-status b.is-demo{color:var(--gs-warn)}
.gs-gap{margin:0;padding:6px 12px;color:var(--gs-warn);font-size:12px;background:var(--gs-card);border-bottom:1px solid var(--gs-line)}
.gs-gap summary{cursor:pointer}
.gs-gap p{margin:6px 0 0}
.gs-scrim{position:fixed;inset:0;z-index:15;border:0;background:transparent;min-height:0}
.gs-canvas{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px;margin:8px 12px 24px;align-items:stretch}
.gs-canvas.is-narrow{grid-template-columns:1fr}
.gs-frame{position:relative;min-width:0;background:var(--gs-card);border:1px solid var(--gs-line);border-radius:2px;display:flex;flex-direction:column;overflow:hidden}
.gs-frame-title{display:flex;align-items:center;min-height:32px;padding:0 12px;border-bottom:1px solid var(--gs-line);background:var(--gs-card)}
.gs-frame-title strong{font-size:13px;font-weight:600;color:var(--gs-ink)}
.gs-frame-body{padding:10px 12px 12px;overflow:auto;min-height:0;flex:1}
.gs-menu{position:absolute;z-index:20;top:calc(100% + 4px);left:0;background:var(--gs-card);border:1px solid var(--gs-line);border-radius:2px;padding:6px;display:flex;flex-direction:column;gap:2px;min-width:220px;max-height:70vh;overflow:auto}
.gs-menu p{margin:4px 8px 6px;font-size:12px;color:var(--gs-muted)}
.gs-menu button{display:flex;align-items:center;gap:8px;text-align:left;padding:0 8px;color:var(--gs-ink);background:transparent;border-radius:2px;min-height:32px}
.gs-menu button i{width:14px;font-style:normal;color:var(--gs-down)}
.gs-menu button.is-on{background:var(--gs-soft)}
.gs-table{width:100%;border-collapse:collapse;font-size:12px}
.gs-table th,.gs-table td{padding:5px 8px;text-align:left;color:var(--gs-ink);border-bottom:1px solid var(--gs-line)}
.gs-table th{color:var(--gs-muted);font-weight:500}
.gs-table th.num,.gs-table td.num{text-align:right}
.gs-sparks{display:flex;flex-direction:column;gap:12px}
.gs-series-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.gs-series-head h3,.gs-money h3,.gs-lanes h3,.gs-stage h3{margin:0;font-size:12px;font-weight:600;color:var(--gs-muted)}
.gs-series-head b{font-size:13px;font-weight:600}
.gs-line{width:100%;height:112px;display:block}
.gs-line line{stroke:var(--gs-line);stroke-width:1;stroke-dasharray:3 3}
.gs-line polyline{fill:none;stroke-width:1.75}
.gs-line polyline.up{stroke:var(--gs-up)}
.gs-line polyline.down{stroke:var(--gs-down)}
.gs-empty,.gs-quiet{color:var(--gs-muted);padding:8px 0;margin:0}
.gs-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
.gs-stats-3{grid-template-columns:repeat(3,minmax(0,1fr));margin-bottom:12px}
.gs-stats span,.gs-dial span{display:block;color:var(--gs-muted);font-size:12px}
.gs-stats b,.gs-dial b{display:block;font-size:22px;line-height:1.2;font-weight:600}
.gs-stats small{display:block;margin-top:2px;color:var(--gs-muted);font-size:12px}
.gs-stats .up b,.gs-dial .up b,.up{color:var(--gs-up)}
.gs-stats .down b,.gs-dial .down b,.down{color:var(--gs-down)}
.gs-dial{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}
.gs-dial div{padding:2px 8px;border-left:2px solid var(--gs-line);min-width:0}
.gs-dial div.up{border-left-color:var(--gs-up)}
.gs-dial div.down{border-left-color:var(--gs-down)}
.gs-hist{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px;align-items:end;min-height:120px}
.gs-hist-col{display:grid;grid-template-rows:18px 72px auto;align-items:end;justify-items:center;gap:4px;min-width:0}
.gs-hist-col b{font-size:12px;font-weight:500}
.gs-hist-col i{align-self:end;display:block;width:100%;max-width:36px;min-height:4px;border-radius:1px 1px 0 0;background:var(--gs-faint)}
.gs-hist-col i.up{background:var(--gs-up)}
.gs-hist-col i.down{background:var(--gs-down)}
.gs-hist-col span{font-size:12px;color:var(--gs-muted);text-align:center;line-height:1.3}
.gs-stage{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.gs-stage em,.gs-chips em,.gs-lanes em,.gs-tomorrow em,.gs-pulse em{display:inline-flex;align-items:center;margin:0 6px 6px 0;padding:2px 6px;background:transparent;color:var(--gs-ink);border:1px solid var(--gs-line);border-radius:2px;font-style:normal;font-size:12px;font-weight:500}
.gs-stage em.is-pocket{color:var(--gs-muted)}
.gs-messages{display:grid;grid-template-columns:72px 1fr;gap:12px;height:100%}
.gs-rail{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.gs-icon{display:inline-flex;align-items:center;justify-content:center;min-width:32px;min-height:24px;padding:0 6px;border-radius:2px;background:transparent;border:1px solid var(--gs-line);color:var(--gs-ink);font-weight:600;font-size:12px}
.gs-rail small{display:block;margin-top:4px;color:var(--gs-muted);font-size:12px}
.gs-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:0 16px;align-content:start}
.gs-cards article,.gs-feed article,.gs-reasons article,.gs-limits article,.gs-fulfill article,.gs-lane-group{background:transparent;padding:8px 0;border:0;border-bottom:1px solid var(--gs-line);border-radius:0;box-shadow:none}
.gs-cards header,.gs-feed header,.gs-reasons header,.gs-limits header,.gs-fulfill header{display:flex;justify-content:space-between;gap:8px;align-items:center}
.gs-cards p,.gs-feed p,.gs-reasons p,.gs-limits p,.gs-pulse p{margin:4px 0 0;color:var(--gs-muted);font-size:13px}
.gs-cards ul{margin:8px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px}
.gs-cards li{display:flex;gap:8px;color:var(--gs-ink);font-size:13px}
.gs-feed{display:flex;flex-direction:column;gap:8px}
.gs-feed input{background:var(--gs-bg);color:inherit;border:1px solid var(--gs-line);border-radius:2px;padding:6px 8px;min-height:32px}
.gs-pulse{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.gs-pulse li{display:grid;grid-template-columns:64px auto 1fr;gap:8px;align-items:start;padding:6px 0;border-bottom:1px solid var(--gs-line)}
.gs-pulse time,.gs-feed time{color:var(--gs-muted);font-size:12px}
.gs-bar-row{display:grid;grid-template-columns:minmax(64px,1.2fr) minmax(48px,1.6fr) max-content;gap:8px;align-items:center;margin:6px 0}
.gs-bars{list-style:none;padding:0;margin:0}
.gs-pair{display:flex;justify-content:space-between;gap:8px;margin:4px 0}
.gs-bar-track{display:block;height:6px;background:var(--gs-track);border-radius:1px}
.gs-bar-track i,.gs-mini i{display:block;height:6px;border-radius:1px}
.gs-bar-track i.up,.gs-mini i.up{background:var(--gs-up)}
.gs-bar-track i.down,.gs-mini i.down{background:var(--gs-down)}
.gs-bar-row b,.gs-pair b{text-align:right;font-weight:500}
.gs-reasons,.gs-limits,.gs-fulfill{display:grid;grid-template-columns:1fr;gap:0}
.gs-lanes{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.gs-lanes-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.gs-lane-group{margin-bottom:8px}
.gs-mini{display:flex;align-items:flex-end;gap:3px;height:32px;margin-top:8px}
.gs-mini i{display:block;width:6px;border-radius:1px 1px 0 0}
.gs-tomorrow b{display:block;font-size:28px;line-height:1.1;font-weight:600;margin-bottom:8px;color:var(--gs-ink)}
.gs-nav-icon{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:2px;border:1px solid var(--gs-line);color:var(--gs-ink);font-weight:600;font-size:12px}
.gs-limits article.up strong{color:var(--gs-up)}
.gs-limits article.down strong{color:var(--gs-down)}
mark{background:transparent;color:var(--gs-ink);font-weight:600}
mark.down{color:var(--gs-down)}
@media (prefers-reduced-motion: reduce){
  .gs-pulse .is-fresh,.gs-feed .is-fresh{animation:none}
}
@media (max-width:840px){
  .gs-top{padding:8px}
  .gs-status{margin-left:0;flex-basis:100%}
  .gs-picker{position:static}
  .gs-menu{position:absolute;left:8px;right:8px;top:100%;width:auto;min-width:0}
  .gs-dial{grid-template-columns:repeat(2,minmax(0,1fr))}
  .gs-stats-3{grid-template-columns:repeat(3,minmax(0,1fr))}
  .gs-hist{grid-template-columns:repeat(3,minmax(0,1fr));min-height:0}
  .gs-messages,.gs-lanes,.gs-lanes-3,.gs-pulse li,.gs-stage{grid-template-columns:1fr}
}
`

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
