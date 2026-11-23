// TS 7은 선언이 없는 부수효과(side-effect) import를 TS2882로 막는다.
// Vite가 CSS를 번들에 넣어 주므로 타입은 비어 있으면 충분하다.
declare module "*.css";
