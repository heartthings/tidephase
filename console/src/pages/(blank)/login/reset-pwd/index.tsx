import { useFormRules } from '@/features/form';
import { useRouter } from '@/features/router';
import { fetchResetPwd } from '@/service/api';

interface FormModel {
  code: string;
  confirmPassword: string;
  password: string;
  phone: string;
}

const ResetPwd = () => {
  const { t } = useTranslation();

  const [form] = AForm.useForm<FormModel>();

  const { navigateUp } = useRouter();

  const { createConfirmPwdRule, formRules } = useFormRules();

  async function handleSubmit(params: FormModel) {
    await fetchResetPwd({
      code: params.code,
      password: params.password,
      phone: params.phone,
      userName: params.phone
    });

    window.$message?.success(t('page.login.common.validateSuccess'));
  }

  useKeyPress('enter', () => {
    form.submit();
  });

  return (
    <>
      <h3 className="text-18px font-medium">{t('page.login.resetPwd.title')}</h3>
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
          <AInput placeholder={t('page.login.common.codePlaceholder')} />
        </AForm.Item>
        <AForm.Item
          name="password"
          rules={formRules.pwd}
        >
          <AInput.Password
            autoComplete="password"
            placeholder={t('page.login.common.passwordPlaceholder')}
          />
        </AForm.Item>
        <AForm.Item
          name="confirmPassword"
          rules={createConfirmPwdRule(form)}
        >
          <AInput.Password
            autoComplete="confirm-password"
            placeholder={t('page.login.common.confirmPasswordPlaceholder')}
          />
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

export default ResetPwd;
