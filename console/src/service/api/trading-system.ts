import { request } from '../request';
import { TRADING_SYSTEM_URLS } from '../urls/trading-system';

export function fetchTradingSystemTree() {
  return request<Api.TradingSystem.TreeResponse>({
    method: 'get',
    url: TRADING_SYSTEM_URLS.TREE
  });
}

export function fetchTradingSystemNode(id: string) {
  return request<Api.TradingSystem.Node>({
    method: 'get',
    url: TRADING_SYSTEM_URLS.GET_NODE(id)
  });
}

export function createTradingSystemNode(params: Api.TradingSystem.CreateNodeParams) {
  return request<Api.TradingSystem.Node>({
    data: params,
    method: 'post',
    url: TRADING_SYSTEM_URLS.CREATE_NODE
  });
}

/** 推荐：按路径 ID 更新（编辑 / 拖拽） */
export function updateTradingSystemNodeById(id: string, params: Api.TradingSystem.UpdateNodeByIdParams) {
  return request<Api.TradingSystem.Node>({
    data: params,
    method: 'put',
    url: TRADING_SYSTEM_URLS.UPDATE_NODE_BY_ID(id)
  });
}

/** 拖拽移动：更新 parentId + sortOrder */
export function moveTradingSystemNode(id: string, params: Api.TradingSystem.MoveNodeParams) {
  const body: Api.TradingSystem.UpdateNodeByIdParams = {
    description: params.description,
    name: params.name,
    parentId: params.parentId,
    sortOrder: params.sortOrder
  };
  if (params.color) {
    body.color = params.color;
  }
  return updateTradingSystemNodeById(id, body);
}

/** @deprecated 请使用 updateTradingSystemNodeById */
export function updateTradingSystemNode(params: Api.TradingSystem.UpdateNodeParams) {
  return request<boolean>({
    data: params,
    method: 'put',
    url: TRADING_SYSTEM_URLS.UPDATE_NODE
  });
}

export function deleteTradingSystemNode(id: string) {
  return request<boolean>({
    method: 'delete',
    url: TRADING_SYSTEM_URLS.DELETE_NODE(id)
  });
}
