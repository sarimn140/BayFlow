import { ShopScope } from '@/components/layout/shop-scope'

/**
 * Shop scope (spec 09 §2.8, spec 10 S-01, D20): for an active member of the shop, the sidebar of
 * their role and the section (or `ForbiddenState` when it belongs to another role, X-03); for
 * anyone else the 404 view, as the API answers. The sidebar state and its toggle live in the POS
 * layout and header. TODO(ShopScope): take the membership from `GET /api/v1/me` once wired, and
 * store `bf:lastShopId`.
 */
export default async function ShopLayout({ children, params }: LayoutProps<'/pos/shops/[shopId]'>) {
  const { shopId } = await params
  return <ShopScope shopId={shopId}>{children}</ShopScope>
}
