import { Card, Empty, Modal, Tabs, TreeSelect } from 'antd';
import type { ECharts } from 'echarts/core';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';

import Markdown from '@/components/Markdown';
import type { ECOption } from '@/hooks/common/echarts';
import { useEcharts } from '@/hooks/common/echarts';
import { useMobile } from '@/hooks/common/mobile';
import { request } from '@/service/request';

interface Neo4jNode {
  group: string;
  id: string;
  topicId: string;
}

interface Neo4jLink {
  relation: string;
  source: string;
  target: string;
}

interface Neo4jData {
  links: Neo4jLink[];
  nodes: Neo4jNode[];
}

interface TopicIntro {
  aiIntroduction?: string;
  briefIntro: string;
  introduction: string;
  name: string;
  topicId: string;
}

interface TopicStockItem {
  reason: string;
  stockId: string;
  stockName: string;
}

interface TopicStockCategory {
  children: TopicStockCategory[];
  id: string;
  name: string;
  stocks: TopicStockItem[];
}

interface TopicCategoryStocksResponse {
  categories: TopicStockCategory[];
  topicId: string;
  topicName: string;
}

interface GroupTreeNode {
  children?: GroupTreeNode[];
  count: number;
  fullPath: string;
  key: string;
  name: string;
  title: string;
}

const GRAPH_COLORS = ['#7C3AED', '#F97316', '#0EA5E9', '#10B981', '#FACC15', '#F472B6', '#6366F1', '#14B8A6'];

export const route = {
  meta: {
    constant: true,
    i18nKey: 'route.(base)_topic-lib',
    icon: 'mdi:chart-bubble',
    order: 4,
    title: 'topic-lib'
  }
};

function splitGroupPath(group: string): string[] {
  if (!group || !group.trim()) {
    return ['未分类'];
  }
  return group
    .split('/')
    .map(part => part.trim())
    .filter(Boolean);
}

function buildGroupTree(nodes: Neo4jNode[]): GroupTreeNode[] {
  type MutableNode = {
    children: Map<string, MutableNode>;
    count: number;
    fullPath: string;
    name: string;
  };

  const root = new Map<string, MutableNode>();

  for (const node of nodes) {
    const parts = splitGroupPath(node.group);
    let cursor = root;
    let path = '';
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      path = path ? `${path}/${part}` : part;
      let child = cursor.get(part);
      if (!child) {
        child = {
          children: new Map(),
          count: 0,
          fullPath: path,
          name: part
        };
        cursor.set(part, child);
      }
      child.count += 1;
      cursor = child.children;
    }
  }

  const toDataNodes = (map: Map<string, MutableNode>): GroupTreeNode[] =>
    Array.from(map.values())
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-CN'))
      .map(item => {
        const children = toDataNodes(item.children);
        return {
          children: children.length > 0 ? children : undefined,
          count: item.count,
          fullPath: item.fullPath,
          key: item.fullPath,
          name: item.name,
          title: `${item.name}（${item.count}）`
        };
      });

  return toDataNodes(root);
}

function getDefaultSelectedPaths(tree: GroupTreeNode[]): string[] {
  if (tree.length === 0) {
    return [];
  }
  const firstMajor = tree[0];
  if (firstMajor.children && firstMajor.children.length > 0) {
    return [firstMajor.children[0].fullPath];
  }
  return [firstMajor.fullPath];
}

function toTreeSelectData(tree: GroupTreeNode[]): {
  children?: { title: string; value: string }[];
  title: string;
  value: string;
}[] {
  return tree.map(node => ({
    children: node.children?.map(child => ({
      title: child.title,
      value: child.fullPath
    })),
    title: node.title,
    value: node.fullPath
  }));
}

function matchGroupPath(group: string, selectedPath: string): boolean {
  const path = splitGroupPath(group).join('/');
  return path === selectedPath || path.startsWith(`${selectedPath}/`);
}

function filterNodesByGroupPaths(nodes: Neo4jNode[], selectedPaths: string[]): Neo4jNode[] {
  if (!selectedPaths.length) {
    return [];
  }
  return nodes.filter(node => selectedPaths.some(path => matchGroupPath(node.group, path)));
}

const GROUP_HUB_PREFIX = '__group__:';

function isGroupHubId(id: string): boolean {
  return id.startsWith(GROUP_HUB_PREFIX);
}

function leafGroupShortName(group: string): string {
  const parts = splitGroupPath(group);
  return parts[parts.length - 1] || group;
}

/** 拖动时只移动同一子分类（叶子 group），避免跨分类被关联边拖走 */
function collectMoveCluster(rootName: string, nodes: { id?: string; name?: string; value?: string }[]): Set<string> {
  const root = nodes.find(node => String(node.id || node.name) === rootName);
  const group = root?.value;
  const cluster = new Set<string>([rootName]);
  if (!group) return cluster;
  for (const node of nodes) {
    if (node.value === group) {
      cluster.add(String(node.id || node.name));
    }
  }
  return cluster;
}

function buildSubcategoryCenters(leafGroups: string[], topicCount: number): Map<string, { x: number; y: number }> {
  const centers = new Map<string, { x: number; y: number }>();
  const n = leafGroups.length;
  if (n === 0) return centers;
  if (n === 1) {
    centers.set(leafGroups[0], { x: 0, y: 0 });
    return centers;
  }
  // 半径适中：子分类彼此分开，又不把画布撑得过大
  const radius = Math.min(360, 140 + n * 26 + Math.sqrt(topicCount) * 6);
  leafGroups.forEach((group, index) => {
    const angle = (Math.PI * 2 * index) / n - Math.PI / 2;
    centers.set(group, {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius
    });
  });
  return centers;
}

function readNodeLayouts(chart: ECharts): Map<string, { x: number; y: number }> {
  const layouts = new Map<string, { x: number; y: number }>();
  try {
    const seriesModel = (chart as any).getModel?.().getSeriesByIndex?.(0);
    const nodeData = seriesModel?.getData?.();
    if (!nodeData) return layouts;
    const count = nodeData.count();
    for (let i = 0; i < count; i += 1) {
      const name = String(nodeData.getId?.(i) ?? nodeData.getName?.(i) ?? '');
      const pt = nodeData.getItemLayout?.(i);
      if (name && pt && Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
        layouts.set(name, { x: pt[0], y: pt[1] });
      }
    }
  } catch {
    // ignore layout read failures
  }
  return layouts;
}

function freezeForceLayout(chart: ECharts) {
  const option = chart.getOption() as any;
  const series = option?.series?.[0];
  if (!series || !Array.isArray(series.data) || series.data.length === 0) return;

  const layouts = readNodeLayouts(chart);
  if (layouts.size === 0) return;

  const nextData = series.data.map((node: any) => {
    const pos = layouts.get(String(node.id || node.name));
    if (!pos) return { ...node, fixed: true };
    return {
      ...node,
      fixed: true,
      x: pos.x,
      y: pos.y
    };
  });

  chart.setOption(
    {
      series: [
        {
          data: nextData,
          layout: 'none'
        }
      ]
    },
    { lazyUpdate: true }
  );
}

interface ClusterDragParams {
  chart: ECharts;
  clusterNames: Set<string>;
  draggedName: string;
  startPositions: Map<string, { x: number; y: number }>;
}

function resolveDragDelta(params: ClusterDragParams): { dx: number; dy: number } | null {
  const layouts = readNodeLayouts(params.chart);
  const current = layouts.get(params.draggedName);
  const start = params.startPositions.get(params.draggedName);
  if (!current || !start) return null;
  const dx = current.x - start.x;
  const dy = current.y - start.y;
  if (dx === 0 && dy === 0) return null;
  return { dx, dy };
}

function applyClusterDragOffset(params: ClusterDragParams): number {
  const delta = resolveDragDelta(params);
  if (!delta) return 0;

  const option = params.chart.getOption() as any;
  const series = option?.series?.[0];
  if (!series || !Array.isArray(series.data)) return 0;

  const nextData = series.data.map((node: any) => {
    const name = String(node.id || node.name);
    const origin = params.clusterNames.has(name) ? params.startPositions.get(name) : undefined;
    if (!origin) {
      return { ...node, fixed: true };
    }
    return {
      ...node,
      fixed: true,
      x: origin.x + delta.dx,
      y: origin.y + delta.dy
    };
  });

  params.chart.setOption(
    {
      series: [
        {
          data: nextData,
          layout: 'none'
        }
      ]
    },
    { lazyUpdate: true }
  );

  return Math.abs(delta.dx) + Math.abs(delta.dy);
}

function buildNameIndexMap(nodeData: any, draggedName: string): { mainIdx: number; nameToIdx: Map<string, number> } {
  const nameToIdx = new Map<string, number>();
  let mainIdx = -1;
  const count = nodeData.count();
  for (let i = 0; i < count; i += 1) {
    const name = String(nodeData.getId?.(i) ?? nodeData.getName?.(i) ?? '');
    nameToIdx.set(name, i);
    if (name === draggedName) {
      mainIdx = i;
    }
  }
  return { mainIdx, nameToIdx };
}

function refreshEdgeLayouts(seriesModel: any) {
  const graph = seriesModel.getGraph?.();
  if (!graph?.eachEdge) return;
  graph.eachEdge((edge: any) => {
    edge.setLayout?.([edge.node1.getLayout(), edge.node2.getLayout()]);
  });
}

/** 拖动过程中让子节点实时跟随父节点平移 */
function syncClusterLayoutsLive(params: ClusterDragParams): number {
  if (params.clusterNames.size <= 1) return 0;
  try {
    const seriesModel = (params.chart as any).getModel?.().getSeriesByIndex?.(0);
    const nodeData = seriesModel?.getData?.();
    if (!nodeData) return 0;

    const { mainIdx, nameToIdx } = buildNameIndexMap(nodeData, params.draggedName);
    if (mainIdx < 0) return 0;

    const mainPt = nodeData.getItemLayout?.(mainIdx);
    const start = params.startPositions.get(params.draggedName);
    if (!mainPt || !start) return 0;

    const dx = mainPt[0] - start.x;
    const dy = mainPt[1] - start.y;
    if (dx === 0 && dy === 0) return 0;

    for (const name of params.clusterNames) {
      if (name !== params.draggedName) {
        const idx = nameToIdx.get(name);
        const origin = params.startPositions.get(name);
        if (idx !== undefined && origin) {
          nodeData.setItemLayout?.(idx, [origin.x + dx, origin.y + dy]);
        }
      }
    }

    refreshEdgeLayouts(seriesModel);
    params.chart.getZr().refresh();
    return Math.abs(dx) + Math.abs(dy);
  } catch {
    return 0;
  }
}

function buildGraphOptions(allData: Neo4jData, selectedPaths: string[]): ECOption {
  const filteredNodes = filterNodesByGroupPaths(allData.nodes, selectedPaths);
  if (!selectedPaths.length || filteredNodes.length === 0) {
    return {
      series: [
        {
          data: [],
          layout: 'none',
          links: [],
          roam: true,
          type: 'graph'
        }
      ]
    };
  }

  const leafGroups = Array.from(new Set(filteredNodes.map(item => item.group || '未分类')));
  const categories = leafGroups.map(name => ({ name }));
  const nameSet = new Set(filteredNodes.map(item => item.id));
  const centers = buildSubcategoryCenters(leafGroups, filteredNodes.length);

  const membersByGroup = new Map<string, Neo4jNode[]>();
  for (const node of filteredNodes) {
    const group = node.group || '未分类';
    const list = membersByGroup.get(group);
    if (list) {
      list.push(node);
    } else {
      membersByGroup.set(group, [node]);
    }
  }

  const conceptNodes: Record<string, unknown>[] = [];
  leafGroups.forEach((group, categoryIndex) => {
    const members = membersByGroup.get(group) || [];
    const center = centers.get(group) || { x: 0, y: 0 };
    const localRadius = Math.min(110, 40 + Math.sqrt(members.length) * 14);
    const hubId = `${GROUP_HUB_PREFIX}${group}`;
    const shortName = leafGroupShortName(group);

    conceptNodes.push({
      category: categoryIndex,
      fixed: true,
      id: hubId,
      isGroupHub: true,
      itemStyle: {
        borderColor: '#ffffff',
        borderWidth: 2,
        opacity: 0.95
      },
      label: {
        fontSize: 13,
        fontWeight: 600,
        position: 'inside',
        show: true
      },
      name: shortName,
      symbol: 'roundRect',
      symbolSize: [Math.max(64, shortName.length * 12), 28],
      value: group,
      x: center.x,
      y: center.y
    });

    members.forEach((node, index) => {
      const angle = members.length === 1 ? 0 : (Math.PI * 2 * index) / members.length;
      conceptNodes.push({
        category: categoryIndex,
        fixed: true,
        id: node.id,
        itemStyle: {
          borderColor: '#ffffff',
          borderWidth: 1
        },
        label: {
          fontSize: 12,
          show: true
        },
        name: node.id,
        symbolSize: Math.min(48, 28 + Math.floor(filteredNodes.length > 40 ? 0 : 6)),
        topicId: node.topicId,
        value: node.group,
        x: center.x + Math.cos(angle) * localRadius,
        y: center.y + Math.sin(angle) * localRadius
      });
    });
  });

  const semanticLinks = allData.links
    .filter(link => nameSet.has(link.source) && nameSet.has(link.target))
    .map(link => ({
      lineStyle: {
        opacity: 0.45
      },
      name: link.relation,
      source: link.source,
      target: link.target
    }));

  // 子分类中心到成员的引导线，方便识别整组
  const hubLinks = leafGroups.flatMap(group => {
    const hubId = `${GROUP_HUB_PREFIX}${group}`;
    return (membersByGroup.get(group) || []).map(node => ({
      lineStyle: {
        curveness: 0,
        opacity: 0.2,
        type: 'dashed' as const,
        width: 1
      },
      name: '',
      source: hubId,
      target: node.id
    }));
  });

  return {
    color: GRAPH_COLORS,
    series: [
      {
        animationDuration: 500,
        animationEasing: 'quinticInOut',
        categories,
        data: conceptNodes,
        draggable: true,
        edgeLabel: {
          fontSize: 10,
          formatter: (params: any) => params.data.name || params.data.relation || '',
          show: filteredNodes.length <= 50
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3
          }
        },
        label: {
          formatter: '{b}',
          position: 'right',
          show: true
        },
        layout: 'none',
        lineStyle: {
          color: 'source',
          curveness: 0.2,
          opacity: 0.55
        },
        links: [...hubLinks, ...semanticLinks],
        roam: true,
        symbol: 'circle',
        type: 'graph'
      }
    ],
    tooltip: {
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          if (params.data?.isGroupHub) {
            return `<b>${params.data.name}</b><br/><span style="color:#94a3b8">${params.data.value}</span><br/>拖动可移动整个子分类`;
          }
          const group = params.data.value ? `<br/><span style="color:#94a3b8">${params.data.value}</span>` : '';
          return `${params.data.name}${group}`;
        }
        if (params.dataType === 'edge') {
          return params.data.name || params.data.relation || '';
        }
        return '';
      },
      trigger: 'item'
    }
  };
}

function renderAiTabContent(introData: TopicIntro) {
  return (
    <div className="space-y-3">
      <div className="rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-800">{introData.briefIntro}</div>
      {introData.aiIntroduction ? (
        <div className="border border-sky-100 rounded-md bg-white px-4 py-4">
          <Markdown value={introData.aiIntroduction} />
        </div>
      ) : (
        <div className="py-8 text-center text-xs text-slate-400">暂无 AI 解析，待该题材增量生成后展示</div>
      )}
    </div>
  );
}

function renderOriginalIntroTab(introData: TopicIntro) {
  return (
    <div className="space-y-4">
      <div className="rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-800">{introData.briefIntro}</div>
      <div
        className="prose max-w-none text-sm leading-relaxed"
        dangerouslySetInnerHTML={{ __html: introData.introduction }}
      />
    </div>
  );
}

function renderStocksTabContent(
  stocksLoading: boolean,
  stocksData: TopicCategoryStocksResponse | null,
  renderStockCategories: (categories: TopicStockCategory[]) => ReactNode
) {
  if (stocksLoading) {
    return <div className="py-6 text-center text-xs text-gray-500">正在加载相关个股...</div>;
  }
  if (!stocksData) {
    return <div className="py-6 text-center text-xs text-slate-400">切换到本页时会加载相关个股</div>;
  }
  if (stocksData.categories.length === 0) {
    return <div className="py-6 text-center text-xs text-slate-400">暂无相关个股数据</div>;
  }
  return (
    <div>
      <div className="mb-3 text-xs text-slate-500">
        题材：{stocksData.topicName}（{stocksData.topicId}）
      </div>
      {renderStockCategories(stocksData.categories)}
    </div>
  );
}

const TopicLibPage = () => {
  const isMobile = useMobile();

  const [rawData, setRawData] = useState<Neo4jData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [introVisible, setIntroVisible] = useState(false);
  const [introLoading, setIntroLoading] = useState(false);
  const [introData, setIntroData] = useState<TopicIntro | null>(null);
  const [activeTab, setActiveTab] = useState<'ai' | 'intro' | 'stocks'>('ai');
  const [stocksLoading, setStocksLoading] = useState(false);
  const [stocksData, setStocksData] = useState<TopicCategoryStocksResponse | null>(null);

  const layoutFrozenRef = useRef(false);
  const skipClickRef = useRef(false);
  const zrMoveHandlerRef = useRef<(() => void) | null>(null);
  const dragSessionRef = useRef<{
    clusterNames: Set<string>;
    name: string;
    startPositions: Map<string, { x: number; y: number }>;
  } | null>(null);

  const groupTree = useMemo(() => (rawData ? buildGroupTree(rawData.nodes) : []), [rawData]);
  const treeSelectData = useMemo(() => toTreeSelectData(groupTree), [groupTree]);
  const visibleTopicCount = useMemo(() => {
    if (!rawData || selectedPaths.length === 0) return 0;
    return filterNodesByGroupPaths(rawData.nodes, selectedPaths).length;
  }, [rawData, selectedPaths]);

  const initialOption: ECOption = useMemo(
    () => ({
      series: [
        {
          data: [],
          layout: 'none',
          links: [],
          roam: true,
          type: 'graph'
        }
      ]
    }),
    []
  );

  function handleNodeClick(params: any) {
    if (skipClickRef.current) {
      skipClickRef.current = false;
      return;
    }
    if (params.dataType !== 'node') return;
    if (params.data?.isGroupHub || isGroupHubId(String(params.data?.id || ''))) return;

    const topicId = (params.data?.topicId as string | undefined) || (params.data?.id as string | undefined);
    if (!topicId) return;

    setIntroVisible(true);
    setIntroLoading(true);
    setIntroData(null);
    setActiveTab('ai');
    setStocksData(null);

    request<TopicIntro>({
      method: 'get',
      params: { topicId },
      url: '/topic/intro'
    })
      .then(data => {
        setIntroData(data);
        setActiveTab(data.aiIntroduction ? 'ai' : 'intro');
      })
      .catch(err => {
        window.$message?.error?.(err?.message || '加载题材简介失败');
      })
      .finally(() => {
        setIntroLoading(false);
      });
  }

  function renderStockCategories(categories: TopicStockCategory[]) {
    return (
      <div className="space-y-4">
        {categories.map(category => (
          <div
            className="border border-slate-200 rounded-md bg-white px-4 py-3"
            key={category.id}
          >
            <div className="mb-2 text-sm text-slate-800 font-semibold">{category.name}</div>
            {category.stocks.length > 0 && (
              <ul className="text-xs text-slate-700 space-y-2">
                {category.stocks.map(stock => (
                  <li
                    className="flex flex-col rounded bg-slate-50 px-3 py-2"
                    key={stock.stockId}
                  >
                    <span className="font-medium">
                      {stock.stockId} {stock.stockName}
                    </span>
                    {stock.reason && <span className="mt-1 text-[11px] text-slate-500">{stock.reason}</span>}
                  </li>
                ))}
              </ul>
            )}
            {category.children.length > 0 && (
              <div className="mt-3 border-l border-slate-200 border-dashed pl-3">
                {renderStockCategories(category.children)}
              </div>
            )}
            {category.stocks.length === 0 && category.children.length === 0 && (
              <div className="text-xs text-slate-400">暂无相关个股</div>
            )}
          </div>
        ))}
      </div>
    );
  }

  function handleTabChange(key: string) {
    if (!introData) return;

    if (key === 'stocks' && !stocksData && !stocksLoading) {
      setStocksLoading(true);
      request<TopicCategoryStocksResponse>({
        method: 'get',
        params: { topicId: introData.topicId },
        url: '/topic/category-stocks'
      })
        .then(data => {
          setStocksData(data);
        })
        .catch(err => {
          window.$message?.error?.(err?.message || '加载相关个股失败');
        })
        .finally(() => {
          setStocksLoading(false);
        });
    }

    setActiveTab(key as 'ai' | 'intro' | 'stocks');
  }

  const { domRef, updateOptions } = useEcharts<ECOption>(() => initialOption, {
    onUpdated: instance => {
      instance.hideLoading();
      instance.off('click');
      instance.off('mousedown');
      instance.off('mouseup');
      instance.off('globalout');
      instance.off('finished');

      instance.on('finished', () => {
        if (layoutFrozenRef.current) return;
        freezeForceLayout(instance);
        layoutFrozenRef.current = true;
      });

      instance.on('mousedown', (params: any) => {
        if (params.dataType !== 'node') return;
        const name = String(params.data?.id || params.data?.name || params.name || '');
        if (!name) return;

        const option = instance.getOption() as any;
        const series = option?.series?.[0];
        const nodes = (series?.data || []) as { id?: string; name?: string; value?: string }[];
        const clusterNames = collectMoveCluster(name, nodes);
        const startPositions = readNodeLayouts(instance);
        if (!startPositions.has(name)) return;

        dragSessionRef.current = {
          clusterNames,
          name,
          startPositions
        };
      });

      const zr = instance.getZr();
      if (zrMoveHandlerRef.current) {
        zr.off('mousemove', zrMoveHandlerRef.current);
      }
      const onZrMove = () => {
        const session = dragSessionRef.current;
        if (!session) return;
        const moved = syncClusterLayoutsLive({
          chart: instance,
          clusterNames: session.clusterNames,
          draggedName: session.name,
          startPositions: session.startPositions
        });
        if (moved > 4) {
          skipClickRef.current = true;
        }
      };
      zrMoveHandlerRef.current = onZrMove;
      zr.on('mousemove', onZrMove);

      const finishDrag = () => {
        const session = dragSessionRef.current;
        if (!session) return;
        dragSessionRef.current = null;

        const moved = applyClusterDragOffset({
          chart: instance,
          clusterNames: session.clusterNames,
          draggedName: session.name,
          startPositions: session.startPositions
        });
        if (moved > 4) {
          skipClickRef.current = true;
          layoutFrozenRef.current = true;
        }
      };

      instance.on('mouseup', finishDrag);
      instance.on('globalout', finishDrag);
      instance.on('click', handleNodeClick);
    }
  });

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    request<Neo4jData>({
      method: 'get',
      timeout: 20000,
      url: '/topic/graph/neo4j-structure'
    })
      .then(data => {
        if (cancelled) return;
        setRawData(data);
        const tree = buildGroupTree(data.nodes);
        setSelectedPaths(getDefaultSelectedPaths(tree));
      })
      .catch(err => {
        if (!cancelled) {
          setError(err?.message || '加载题材库数据失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!rawData) return;
    layoutFrozenRef.current = false;
    dragSessionRef.current = null;
    const option = buildGraphOptions(rawData, selectedPaths);
    updateOptions(() => option);
  }, [rawData, selectedPaths, updateOptions]);

  function handleTreeSelectChange(value: string | string[]) {
    if (Array.isArray(value)) {
      setSelectedPaths(value.map(String));
      return;
    }
    setSelectedPaths(value ? [String(value)] : []);
  }

  return (
    <Card
      className="card-wrapper"
      title="题材库知识图谱"
      variant="borderless"
    >
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="shrink-0 text-sm text-slate-700 font-medium">题材分类（多选）</div>
        <TreeSelect
          allowClear
          showSearch
          treeCheckable
          treeDefaultExpandAll
          className="min-w-0 flex-1"
          dropdownStyle={{ maxHeight: 460, overflow: 'auto', paddingBottom: 12 }}
          listHeight={420}
          maxTagCount="responsive"
          placeholder="可多选：一级整类，或跨类多个二级"
          popupClassName="topic-group-tree-dropdown"
          showCheckedStrategy={TreeSelect.SHOW_PARENT}
          style={{ width: '100%' }}
          treeData={treeSelectData}
          value={selectedPaths}
          virtual={false}
          filterTreeNode={(input, node) => {
            const keyword = input.trim().toLowerCase();
            if (!keyword) return true;
            const value = String(node.value || '').toLowerCase();
            const title = String(node.title || '').toLowerCase();
            return value.includes(keyword) || title.includes(keyword);
          }}
          onChange={handleTreeSelectChange}
        />
      </div>

      <style>{`
        .topic-group-tree-dropdown .ant-select-tree-list {
          min-height: 120px;
        }
        .topic-group-tree-dropdown .ant-select-tree-list-holder {
          max-height: 420px !important;
          overflow-y: auto !important;
        }
        .topic-group-tree-dropdown .ant-select-tree-list-holder-inner {
          padding-bottom: 12px;
        }
        .topic-group-tree-dropdown .ant-select-tree-node-content-wrapper {
          white-space: nowrap;
        }
        .topic-group-tree-dropdown .ant-select-tree-title {
          overflow: visible;
        }
      `}</style>

      <div className={isMobile ? 'relative h-[65vh] w-full' : 'relative h-[72vh] w-full'}>
        {(loading || error) && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center text-xs">
            {loading ? (
              <span className="text-gray-500">正在加载题材库数据...</span>
            ) : (
              <span className="text-red-500">加载题材库数据失败：{error}</span>
            )}
          </div>
        )}
        {!loading && !error && selectedPaths.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-slate-50">
            <Empty description="请在顶部多选分类后查看图谱" />
          </div>
        )}
        <div
          className="h-full w-full rounded-lg bg-slate-50"
          ref={domRef}
        />
      </div>

      <div className="mt-3 text-xs text-gray-500">
        {selectedPaths.length > 0
          ? `已选 ${selectedPaths.length} 个分类，展示题材 ${visibleTopicCount} 个。每个子分类已分区排布；拖动圆角标签（子分类名）或其下任意题材，可整组挪开，不会带动其他子分类。`
          : '请在顶部勾选分类：支持一个/多个一级，或一个一级下多个二级，或跨一级组合二级。'}
      </div>
      <Modal
        bodyStyle={{ maxHeight: '70vh', overflowY: 'auto' }}
        footer={null}
        open={introVisible}
        title={introData?.name || '题材简介'}
        width={isMobile ? 480 : 720}
        onCancel={() => setIntroVisible(false)}
      >
        {introLoading && <div className="py-6 text-center text-xs text-gray-500">正在加载题材简介...</div>}
        {!introLoading && introData && (
          <Tabs
            activeKey={activeTab}
            items={[
              {
                children: renderAiTabContent(introData),
                key: 'ai',
                label: 'AI解析'
              },
              {
                children: renderOriginalIntroTab(introData),
                key: 'intro',
                label: '原始详情'
              },
              {
                children: (
                  <div className="space-y-4">
                    {renderStocksTabContent(stocksLoading, stocksData, renderStockCategories)}
                  </div>
                ),
                key: 'stocks',
                label: '相关个股'
              }
            ]}
            onChange={handleTabChange}
          />
        )}
      </Modal>
    </Card>
  );
};

export default TopicLibPage;
