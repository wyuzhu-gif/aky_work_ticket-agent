import { makeStyles, tokens } from '@fluentui/react-components'

/** FluentUI 共享样式 - 智能问数 + hermes 问答共用 */
export const useChatStyles = makeStyles({
  root: {
    display: 'flex',
    height: 'calc(100vh - 96px)',
    gap: '0',
  },
  sidebar: {
    width: '260px',
    minWidth: '260px',
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: tokens.colorNeutralBackground2,
    overflow: 'hidden',
  },
  sidebarHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 12px 8px',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  sidebarList: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 0',
  },
  sessionItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 12px',
    cursor: 'pointer',
    borderLeft: '3px solid transparent',
    transition: 'background 0.15s, border-color 0.15s',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  sessionItemActive: {
    backgroundColor: tokens.colorBrandBackground2,
    borderLeftColor: tokens.colorBrandStroke1,
  },
  sessionTitle: {
    flex: 1,
    fontSize: '13px',
    lineHeight: '20px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: tokens.colorNeutralForeground1,
  },
  sessionTime: {
    fontSize: '10px',
    color: tokens.colorNeutralForeground3,
    marginTop: '2px',
  },
  sessionDelete: {
    opacity: 0,
    transition: 'opacity 0.15s',
    minWidth: '24px',
    padding: '0',
  },
  sessionItemHover: {
    [`&:hover .sessionDelete`]: {
      opacity: 1,
    },
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '8px',
    padding: '0 4px',
  },
  title: { fontSize: '20px', fontWeight: 700, color: tokens.colorBrandForeground1 },
  messagesArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 0',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  msgBubble: {
    // 2026-06-25: 改大 maxWidth 让 chart/table 完整展示
    // 之前 85% 导致 chart 被挤窄 (尤其水平 bar 图, 5+ 个场所时)
    maxWidth: '95%',
    padding: '12px 16px',
    borderRadius: '12px',
    fontSize: '14px',
    lineHeight: '22px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  // AI 回答的 bubble 单独再加宽 (chart 专属)
  // 让 chart 有充足横向空间, 不被窄气泡挤
  aiBubbleWide: {
    alignSelf: 'flex-start',
    backgroundColor: tokens.colorNeutralBackground1,
    color: tokens.colorNeutralForeground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    maxWidth: '98%',  // 接近满宽
    minWidth: 600,     // 最小宽度, 防止小屏挤压
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
    border: `1px solid ${tokens.colorBrandStroke2}`,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: tokens.colorNeutralBackground1,
    color: tokens.colorNeutralForeground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  stepsWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    marginBottom: '8px',
    padding: '8px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  dataSection: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
    overflowX: 'auto',
  },
  sqlTag: {
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
    marginTop: '4px',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap',
    maxHeight: '80px',
    overflowY: 'auto',
  },
  inputArea: {
    display: 'flex',
    gap: '8px',
    paddingTop: '8px',
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  inputField: { flex: 1 },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    color: tokens.colorNeutralForeground3,
  },
  emptyIcon: { fontSize: '48px', opacity: 0.5 },
  chartWrap: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
    // 2026-06-25: 工程级修复 (你提示的 6 步方案)
    // min-width: 0 突破 flex item 默认 min-width: auto (反向收缩根因)
    width: '100% !important',
    minWidth: 0,
    display: 'block',  // 强制 block 布局, 不参与外层 flex
  },
  answerWrap: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    border: `1px solid ${tokens.colorBrandStroke2}`,
    backgroundColor: tokens.colorNeutralBackground1,
  },
  answerTitle: {
    fontSize: '12px',
    fontWeight: 600,
  },
})
