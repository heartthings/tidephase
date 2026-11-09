import { Navigate } from 'react-router-dom';

/** 市场动向入口落到大盘直播。 */
export default function MarketTrends() {
  return (
    <Navigate
      replace
      to="/market-trends/radar"
    />
  );
}
