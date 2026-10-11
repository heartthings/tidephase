import { useFormRules } from '@/features/form';
import { useRouter } from '@/features/router';
import { fetchRegister } from '@/service/api';

interface FormModel {
  code: string;
  confirmPassword: string;
  password: string;
  phone: string;
}

const Register = () => {
  const { t } = useTranslation();

  const { getCaptcha, isCounting, label, loading } = useCaptcha();

  const { navigateUp } = useRouter();

  const [form] = AForm.useForm<FormModel>();

  const { createConfirmPwdRule, formRules } = useFormRules();

  async function handleSubmit(params: FormModel) {
    await fetchRegister({
      code: params.code,
      password: params.password,
      phone: params.phone,
      userName: params.phone
    });

    window.$message?.success(t('page.login.common.validateSuccess'));
  }

  function sendCaptcha() {
    getCaptcha('17260711111');
  }

  useKeyPress('enter', () => {
    form.submit();
  });

  return (
    <>
      <h3 className="text-18px font-medium">{t('page.login.register.title')}</h3>
      <AForm
        className="pt-24px"
        form={form}
        onFinish={handleSubmit}
      >
        <AForm.Item
          name="phone"
          rules={formRules.phone}
        >
          <AInput placeholder={t('page.login.common.phonePlaceholder')} />
        </AForm.Item>
        <AForm.Item
          name="code"
          rules={formRules.code}
        >
          <div className="w-full flex-y-center gap-16px">
            <AInput placeholder={t('page.login.common.codePlaceholder')} />
            <AButton
              disabled={isCounting}
              loading={loading}
              size="large"
              onClick={sendCaptcha}
            >
              {label}
            </AButton>
          </div>
        </AForm.Item>
        <AForm.Item
          name="password"
          rules={formRules.pwd}
        >
          <AInput placeholder={t('page.login.common.passwordPlaceholder')} />
        </AForm.Item>
        <AForm.Item
          name="confirmPassword"
          rules={createConfirmPwdRule(form)}
        >
          <AInput placeholder={t('page.login.common.confirmPasswordPlaceholder')} />
        </AForm.Item>
        <ASpace
          className="w-full"
          direction="vertical"
          size={18}
        >
          <AButton
            block
            htmlType="submit"
            shape="round"
            size="large"
            type="primary"
          >
            {t('common.confirm')}
          </AButton>

          <AButton
            block
            shape="round"
            size="large"
            onClick={navigateUp}
          >
            {t('page.login.common.back')}
          </AButton>
        </ASpace>
      </AForm>
    </>
  );
};

export default Register;
