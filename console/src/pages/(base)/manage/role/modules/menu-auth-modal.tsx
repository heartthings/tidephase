import { SimpleScrollbar } from '@sa/materials';
import type { DataNode } from 'antd/es/tree';
import { useMemo } from 'react';

import { useAllPages, useMenuTree } from '@/service/hooks/useSystemManage';

import type { ModulesProps } from './type';

const MenuAuthModal: FC<ModulesProps> = memo(({ onClose, open, roleId }) => {
  const { t } = useTranslation();

  const title = t('common.edit') + t('page.manage.role.menuAuth');

  const { data: allPages = [], isLoading: isLoadingPages } = useAllPages();
  const { data: menuTree = [], isLoading: isLoadingTree } = useMenuTree();

  const [home, setHome] = useState<string>();
  const [checks, setChecks] = useState<number[]>();

  // 将后端返回的页面列表转换为选项格式
  const pageSelectOptions = useMemo(() => {
    return allPages.map(page => ({
      label: page,
      value: page
    }));
  }, [allPages]);

  // 将后端返回的菜单树转换为 Ant Design Tree 需要的格式
  const treeData = useMemo<DataNode[]>(() => {
    function convertMenuTreeToDataNode(menu: Api.SystemManage.MenuTree): DataNode {
      return {
        children: menu.children?.map(convertMenuTreeToDataNode),
        key: menu.id,
        title: menu.label
      };
    }

    return menuTree.map(convertMenuTreeToDataNode);
  }, [menuTree]);

  async function getChecks() {
    // request - 获取角色已选中的菜单项
    // const { data } = await fetchGetRoleMenuAuth(roleId);
    // setChecks(data.menuIds);

    console.log(roleId);
    setChecks([]);
  }

  async function getHome() {
    // request - 获取角色的首页
    // const { data } = await fetchGetRoleHome(roleId);
    // setHome(data.home);

    console.log(roleId);
    setHome('');
  }

  function handleSubmit() {
    // request - 更新角色菜单权限
    // await fetchUpdateRoleMenuAuth({ roleId, menuIds: checks, home });

    console.log(checks, roleId, home);

    window.$message?.success?.(t('common.modifySuccess'));

    onClose();
  }

  async function init() {
    await Promise.all([getHome(), getChecks()]);
  }

  useUpdateEffect(() => {
    if (open) {
      init();
    }
  }, [open]);

  return (
    <AModal
      className="w-480px"
      open={open}
      title={title}
      footer={
        <ASpace className="mt-16px">
          <AButton
            size="small"
            onClick={onClose}
          >
            {t('common.cancel')}
          </AButton>
          <AButton
            size="small"
            type="primary"
            onClick={handleSubmit}
          >
            {t('common.confirm')}
          </AButton>
        </ASpace>
      }
      onCancel={onClose}
    >
      <div className="flex-y-center gap-16px pb-12px">
        <div>{t('page.manage.menu.home')}</div>

        <ASelect
          className="w-240px"
          loading={isLoadingPages}
          options={pageSelectOptions}
          size="small"
          value={home}
          onChange={setHome}
        />
      </div>

      <SimpleScrollbar className="!h-270px">
        {isLoadingTree ? (
          <div className="h-280px flex-center">
            <ASpin />
          </div>
        ) : (
          <ATree
            blockNode
            checkable
            checkedKeys={checks}
            className="h-280px"
            treeData={treeData}
            onCheck={value => setChecks(value as number[])}
          />
        )}
      </SimpleScrollbar>
    </AModal>
  );
});

export default MenuAuthModal;
