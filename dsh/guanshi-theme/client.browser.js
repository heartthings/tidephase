window.__ModuleLoader__.load({id: "guanshi-theme", factory: function () {
  const module = { exports: {} };
  const pair = (light, dark) => ({ light: light, dark: dark });
  const tokens = {
    "--dsw-alias-bg-base": pair("#F8FAFC", "#0F172A"),
    "--dsw-alias-bg-layer-1": pair("#FFFFFF", "#1E293B"),
    "--dsw-alias-bg-layer-2": pair("#F1F5F9", "#334155"),
    "--dsw-alias-bg-overlay": pair("#FFFFFF", "#1E293B"),
    "--dsw-alias-border-l1": pair("#E2E8F0", "#334155"),
    "--dsw-alias-border-l2": pair("#CBD5E1", "#475569"),
    "--dsw-alias-brand-primary": pair("#4F46E5", "#818CF8"),
    "--dsw-alias-label-primary": pair("#1F2937", "#F8FAFC"),
    "--dsw-alias-label-secondary": pair("#6B7280", "#CBD5E1"),
    "--dsw-alias-state-error-primary": pair("#EF4444", "#F87171"),
    "--dsw-alias-state-idle-primary": pair("#9CA3AF", "#94A3B8"),
    "--dsw-alias-state-success-primary": pair("#10B981", "#34D399"),
    "--dsw-alias-state-warn-primary": pair("#F59E0B", "#FBBF24"),
    "--dsw-specific-sidebar-fill": pair("#FFFFFF", "#0F172A")
  };
  const css = [
    "body{--dsw-font-family:\"PingFang SC\",\"Noto Sans SC\",\"Microsoft YaHei\",sans-serif;",
    "--dsw-font-family-brand:\"PingFang SC\",\"Noto Sans SC\",sans-serif;}"
  ].join("");

  module.exports.name = "guanshi-theme-client";
  module.exports.inject = ["theme"];
  module.exports.apply = function (ctx) {
    let stop = function () {};
    try {
      stop = ctx.theme.overrideTokens("guanshi-theme", tokens);
    } catch (error) {
      console.warn("[guanshi-theme] token override skipped", error);
    }
    const style = document.createElement("style");
    style.setAttribute("data-guanshi-theme", "soft-ui");
    style.textContent = css;
    document.head.appendChild(style);
    if (typeof ctx.effect === "function") {
      ctx.effect(function () {
        return function () {
          stop();
          style.remove();
        };
      });
    }
  };
  return module.exports;
}});
