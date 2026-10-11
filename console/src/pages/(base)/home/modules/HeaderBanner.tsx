import avatar from '@/assets/imgs/mark.jpg';
import { useUserInfo } from '@/service/hooks';

const HeaderBanner = () => {
  const { t } = useTranslation();

  const { data: userInfo } = useUserInfo();

  return (
    <ACard
      className="card-wrapper"
      variant="borderless"
    >
      <ARow gutter={[16, 16]}>
        <ACol span={24}>
          <div className="flex-y-center">
            <div className="size-72px shrink-0 overflow-hidden rd-1/2">
              <img
                className="size-full"
                src={avatar}
              />
            </div>
            <div className="pl-12px">
              <h3 className="text-18px font-semibold">{t('page.home.greeting', { userName: userInfo?.userName })}</h3>
              <p className="text-#999 leading-30px">{t('page.home.weatherDesc')}</p>
            </div>
          </div>
        </ACol>
      </ARow>
    </ACard>
  );
};

export default HeaderBanner;
