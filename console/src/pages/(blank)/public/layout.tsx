import { Outlet } from 'react-router-dom';

/** Path segment layout so nested `/public/catalyst` can render through. */
export default function PublicLayout() {
  return <Outlet />;
}
