import { loginModuleRecord } from '@/constants/app';
import { useInitAuth } from '@/features/auth/auth';
import { useFormRules } from '@/features/form';

type LoginParams = {
  password: string;
  userName: string;
};

const INITIAL_VALUES = {
  password: '',
  userName: ''
};

const PwdLogin = () => {
  const { t } = useTranslation();

  const { loading, toLogin } = useInitAuth();

  const [form] = AForm.useForm<LoginParams>();

  const navigate = useNavigate();

  const {
    formRules: { pwd, userName: userNameRules }
  } = useFormRules();

  function goRegister() {
    navigate('register');
  }

  function goResetPwd() {
    navigate('reset-pwd');
  }

  useKeyPress('enter', () => {
    form.submit();
  });

  return (
    <>
      <h3 className="text-18px font-medium">{t('page.login.pwdLogin.title')}</h3>
      <AForm
        className="pt-24px"
        form={form}
        initialValues={INITIAL_VALUES}
        onFinish={toLogin}
      >
        <AForm.Item
          name="userName"
          rules={userNameRules}
        >
          <AInput />
        </AForm.Item>

        <AForm.Item
          name="password"
          rules={pwd}
        >
          <AInput.Password autoComplete="password" />
        </AForm.Item>
        <ASpace
          className="w-full"
          direction="vertical"
          size={24}
        >
          <div className="flex-y-center justify-between">
            <ACheckbox>{t('page.login.pwdLogin.rememberMe')}</ACheckbox>

            <AButton
              type="text"
              onClick={goResetPwd}
            >
              {t('page.login.pwdLogin.forgetPassword')}
            </AButton>
          </div>
          <AButton
            block
            color="primary"
            htmlType="submit"
            loading={loading}
            shape="round"
            size="large"
            type="primary"
          >
            {t('common.confirm')}
          </AButton>
          <div className="flex-center pt-8px">
            <AButton
              type="link"
              onClick={goRegister}
            >
              {t(loginModuleRecord.register)}
            </AButton>
          </div>
        </ASpace>
      </AForm>
    </>
  );
};

export default PwdLogin;
