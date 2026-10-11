export interface TradingSystemNode {
  children: TradingSystemNode[];
  color: string | null;
  createdTime?: string;
  description: string;
  id: string;
  level: number;
  name: string;
  parentId: string;
  sortOrder: number;
  updatedTime?: string;
}

export type NodeOperateType = 'add' | 'addChild' | 'edit';

export interface NodeFormValues {
  color?: string;
  description: string;
  name: string;
}
