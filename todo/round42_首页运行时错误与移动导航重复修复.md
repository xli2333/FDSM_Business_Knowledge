# Round42 首页运行时错误与移动导航重复修复

## 目标

修复本轮首页改动引入的两个前端运行时问题：
- 修复 `assistantCard` 在初始化前被引用导致的页面报错
- 修复移动端导航重复拼接造成的重复 key 警告
- 保持当前首页首屏结构与导航信息架构不回退

## 原子任务

- [x] P0 | 首页运行时 | 调整 `HomePage.jsx` 中变量声明顺序，消除 `assistantCard` 引用错误
- [x] P0 | 导航稳定性 | 修复移动端导航重复路径导致的重复 key 与重复入口
- [x] P1 | 验收 | 运行前端构建与 lint，确认无新增报错
- [x] P1 | 回填 | 按完成情况逐项勾选并记录本轮结论

## 本轮结论

- 已修复 [HomePage.jsx](C:\Users\LXG\fdsmarticles\frontend\src\pages\HomePage.jsx) 中 `assistantCard` 在声明前被引用导致的运行时错误
- 已修复 [Navbar.jsx](C:\Users\LXG\fdsmarticles\frontend\src\components\layout\Navbar.jsx) 中移动端导航重复拼接 `/me` 等路径导致的重复 key 与重复入口
- 已通过 `npm.cmd run build` 与 `npm.cmd run lint`
- 这轮属于回归修复，当前没有新的明确报错残留；你刷新后如果还有新的验收问题，我继续按下一轮 Todo 处理
