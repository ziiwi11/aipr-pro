/** Refresh completed export results without rebuilding outreach drafts or selection. */
export function replaceDeliverySection(root:HTMLElement, render:()=>HTMLElement):boolean {
  const section=root.querySelector(".delivery-center-page");
  if(!section)return false;
  section.replaceWith(render());
  return true;
}
