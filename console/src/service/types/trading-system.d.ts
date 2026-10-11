/** 命名空间 Api.TradingSystem */
declare namespace Api {
  namespace TradingSystem {
    /** 树节点 */
    interface Node {
      children?: Node[];
      color: string | null;
      createdTime?: string;
      description: string | null;
      id: string;
      level: number;
      name: string;
      parentId: string;
      sortOrder: number;
      updatedTime?: string;
    }

    /** GET /trading-system/tree */
    interface TreeResponse {
      maxLevel: number;
      nodes: Node[];
    }

    /** POST /trading-system/node */
    interface CreateNodeParams {
      color?: string;
      description?: string;
      name: string;
      parentId?: string;
      sortOrder?: number;
    }

    /** PUT /trading-system/node/{id} */
    interface UpdateNodeByIdParams {
      color?: string;
      description?: string;
      name: string;
      /** 拖拽排序 / 调整父级时使用 */
      parentId?: string;
      sortOrder?: number;
    }

    /** PUT /trading-system/node（兼容，不推荐） */
    interface UpdateNodeParams {
      description?: string;
      id: string;
      name: string;
      sortOrder?: number;
    }

    /** 拖拽移动节点 */
    interface MoveNodeParams {
      color?: string;
      description?: string;
      name: string;
      parentId: string;
      sortOrder: number;
    }
  }
}
