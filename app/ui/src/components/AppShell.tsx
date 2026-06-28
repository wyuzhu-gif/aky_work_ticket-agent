import {
  Button,
  Input,
  makeStyles,
  mergeClasses,
  tokens,
} from '@fluentui/react-components'
import {
  BoardRegular,
  SearchRegular,
  ShieldCheckmarkRegular,
  BookRegular,
  ClipboardTaskRegular,
  DataUsageRegular,
  WeatherMoonRegular,
  WeatherSunnyRegular,
  SettingsRegular,
  BrainCircuitRegular,
  DocumentTextRegular,
  ChartMultipleRegular,
  DocumentRegular,
  ChevronDown16Regular,
  ChevronRight16Regular,
  ChatRegular,
} from '@fluentui/react-icons'
import { PropsWithChildren, useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import type { ThemeMode } from '../theme'

type AppShellProps = PropsWithChildren<{
  mode: ThemeMode
  onToggleMode: () => void
}>

const useStyles = makeStyles({
  shell: {
    minHeight: '100vh',
    color: tokens.colorNeutralForeground1,
  },
  layout: {
    display: 'grid',
    gridTemplateColumns: '260px 1fr',
    minHeight: '100vh',
  },
  // ========== SIDEBAR ==========
  nav: {
    padding: '20px 16px',
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    backdropFilter: 'blur(12px)',
    backgroundColor: tokens.colorNeutralBackground2,
    overflowY: 'auto',
  },
  // ========== BRAND ==========
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '14px 12px',
    borderRadius: '12px',
    backgroundColor: tokens.colorBrandBackground2,
    border: `1px solid ${tokens.colorBrandStroke2}`,
    marginBottom: '20px',
  },
  brandIcon: {
    width: '40px',
    height: '40px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '10px',
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
    fontSize: '20px',
  },
  brandInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: tokens.colorPaletteGreenBackground3,
    boxShadow: `0 0 6px ${tokens.colorPaletteGreenBackground3}`,
  },
  brandTitle: {
    fontSize: '14px',
    fontWeight: 700,
    color: tokens.colorBrandForeground1,
  },
  brandSub: {
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
  },
  // ========== NAV ITEMS ==========
  navSectionTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 12px',
    fontSize: '12px',
    fontWeight: 600,
    color: tokens.colorNeutralForeground3,
    letterSpacing: '0.03em',
    marginTop: '8px',
    cursor: 'pointer',
    userSelect: 'none',
    borderRadius: '6px',
    transitionProperty: 'background-color',
    transitionDuration: '150ms',
    '&:hover': {
      backgroundColor: tokens.colorSubtleBackgroundHover,
    },
  },
  navSectionIcon: {
    fontSize: '14px',
    color: tokens.colorNeutralForeground3,
  },
  navSectionChevron: {
    fontSize: '12px',
    marginLeft: 'auto',
    color: tokens.colorNeutralForeground3,
    transitionProperty: 'transform',
    transitionDuration: '200ms',
  },
  navSubItems: {
    overflow: 'hidden',
    transitionProperty: 'max-height, opacity',
    transitionDuration: '200ms',
  },
  navSubItemsCollapsed: {
    maxHeight: '0 !important',
    opacity: 0,
  },
  navSubItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 12px 8px 40px',
    borderRadius: '8px',
    textDecoration: 'none',
    color: tokens.colorNeutralForeground2,
    border: '1px solid transparent',
    transitionProperty: 'all',
    transitionDuration: '150ms',
    '&:hover': {
      backgroundColor: tokens.colorSubtleBackgroundHover,
      color: tokens.colorNeutralForeground1,
    },
  },
  navSubItemActive: {
    backgroundColor: tokens.colorBrandBackground2,
    border: `1px solid ${tokens.colorBrandStroke1}`,
    color: tokens.colorNeutralForeground1,
    fontWeight: 500,
  },
  navSubItemIcon: {
    fontSize: '16px',
    color: tokens.colorBrandForeground1,
  },
  // ========== CONTENT ==========
  content: {
    display: 'grid',
    gridTemplateRows: '56px 1fr',
    minWidth: 0,
  },
  // ========== TOP BAR ==========
  topbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground1,
    backdropFilter: 'blur(12px)',
  },
  titleSection: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  backButton: {
    minWidth: 'auto',
  },
  pageTitle: {
    fontSize: '16px',
    fontWeight: 600,
    color: tokens.colorBrandForeground1,
  },
  breadcrumbs: {
    fontSize: '12px',
    color: tokens.colorNeutralForeground3,
  },
  // ========== ACTIONS ==========
  actions: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center',
  },
  search: {
    width: '280px',
    maxWidth: '30vw',
  },
  searchWrapper: {
    position: 'relative',
  },
  searchDropdown: {
    position: 'absolute',
    top: '100%',
    right: 0,
    width: '320px',
    maxHeight: '300px',
    overflowY: 'auto',
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '8px',
    boxShadow: tokens.shadow16,
    zIndex: 1000,
    marginTop: '4px',
  },
  searchItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 14px',
    cursor: 'pointer',
    textDecoration: 'none',
    color: tokens.colorNeutralForeground1,
    '&:hover': {
      backgroundColor: tokens.colorSubtleBackgroundHover,
    },
  },
  searchItemIcon: {
    fontSize: '16px',
    color: tokens.colorBrandForeground1,
    flexShrink: 0,
  },
  searchItemName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    fontSize: '13px',
  },
  searchItemHint: {
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
  },
  searchEmpty: {
    padding: '16px',
    textAlign: 'center',
    fontSize: '13px',
    color: tokens.colorNeutralForeground3,
  },
  // ========== PAGE ==========
  page: {
    padding: '20px',
    minWidth: 0,
    overflowY: 'auto',
  },
})

/** 导航分区定义 (2026-06-12 简化为 3 大功能) */
const NAV_SECTIONS = [
  {
    title: '作业票管理',
    icon: <ClipboardTaskRegular />,
    items: [
      { to: '/ticket-review', label: '作业票审查', icon: <DocumentRegular /> },
    ],
  },
  {
    title: '数据分析',
    icon: <DataUsageRegular />,
    items: [
      { to: '/smart-query', label: '智能问数', icon: <DataUsageRegular /> },
      { to: '/hermes-chat', label: 'Hermes 问答', icon: <ChatRegular /> },
    ],
  },
  {
    title: '系统管理',
    icon: <SettingsRegular />,
    items: [
      { to: '/agent-admin', label: '智能体配置', icon: <BrainCircuitRegular /> },
    ],
  },
] as const

/** 路径 → 页面标题 映射 */
const PAGE_TITLES: Record<string, string> = {
  '/ticket-review': '作业票审查',
  '/smart-query': '智能问数',
  '/hermes-chat': 'Hermes 问答',
  '/agent-admin': '智能体配置',
}

/** 路径 → 所属分区 映射 */
const PAGE_BREADCRUMBS: Record<string, string> = {
  '/ticket-review': '作业票管理',
  '/smart-query': '数据分析',
  '/agent-admin': '系统管理',
}

export function AppShell({ mode, onToggleMode, children }: AppShellProps) {
  const classes = useStyles()
  const location = useLocation()
  const navigate = useNavigate()

  // 折叠状态：记录每个分区的展开/折叠
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const toggleSection = (title: string) => {
    setCollapsed(prev => ({ ...prev, [title]: !prev[title] }))
  }

  // 全局搜索状态
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [fileList, setFileList] = useState<string[]>([])

  // 加载文件列表（懒加载，首次聚焦搜索框时获取）
  const filesLoaded = useRef(false)
  const loadFiles = useCallback(async () => {
    if (filesLoaded.current) return
    try {
      const API_BASE = import.meta.env.VITE_API_BASE || ''
      const res = await fetch(`${API_BASE}/api/v1/files`)
      if (res.ok) {
        const files: string[] = await res.json()
        setFileList(files)
        filesLoaded.current = true
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (searchQuery && !filesLoaded.current) loadFiles()
  }, [searchQuery, loadFiles])

  // 有查询关键词时自动打开下拉
  useEffect(() => {
    setSearchOpen(searchQuery.trim().length > 0)
  }, [searchQuery])

  const filteredFiles = searchQuery.trim()
    ? fileList.filter(f => f.toLowerCase().includes(searchQuery.toLowerCase())).slice(0, 8)
    : []

  const basePath = '/' + location.pathname.split('/').filter(Boolean)[0] || '/'
  const pageTitle = PAGE_TITLES[basePath] || PAGE_TITLES[location.pathname] || 'AI 文档审核'
  const breadcrumb = PAGE_BREADCRUMBS[basePath] || PAGE_BREADCRUMBS[location.pathname] || ''

  const isTopLevel = ['/ticket-review', '/smart-query', '/hermes-chat', '/agent-admin'].includes(basePath)

  return (
    <div className={classes.shell}>
      <div className={classes.layout}>
        <aside className={classes.nav}>
          {/* Brand */}
          <div className={classes.brand}>
            <div className={classes.brandIcon}>
              <ShieldCheckmarkRegular />
            </div>
            <div className={classes.brandInfo}>
              <div className={classes.statusRow}>
                <span className={classes.statusDot} />
                <span className={classes.brandTitle}>作业票审查系统</span>
              </div>
              <span className={classes.brandSub}>智能审阅 · 风险识别</span>
            </div>
          </div>

          {/* Nav Sections */}
          {NAV_SECTIONS.map((section) => {
            const isCollapsed = collapsed[section.title] ?? false
            return (
              <div key={section.title}>
                <div className={classes.navSectionTitle} onClick={() => toggleSection(section.title)}>
                  <span className={classes.navSectionIcon}>{section.icon}</span>
                  <span>{section.title}</span>
                  <span className={classes.navSectionChevron}>
                    {isCollapsed ? <ChevronRight16Regular /> : <ChevronDown16Regular />}
                  </span>
                </div>
                <div
                  className={mergeClasses(classes.navSubItems, isCollapsed && classes.navSubItemsCollapsed)}
                  style={{ maxHeight: isCollapsed ? 0 : `${section.items.length * 48}px` }}
                >
                  {section.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        mergeClasses(classes.navSubItem, isActive && classes.navSubItemActive)
                      }
                    >
                      <span className={classes.navSubItemIcon}>{item.icon}</span>
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          })}
        </aside>

        <div className={classes.content}>
          <header className={classes.topbar}>
            <div className={classes.titleSection}>
              {!isTopLevel && (
                <Button
                  appearance="subtle"
                  size="small"
                  className={classes.backButton}
                  onClick={() => navigate(-1)}
                >
                  ← 返回
                </Button>
              )}
              <span className={classes.pageTitle}>{pageTitle}</span>
              {breadcrumb && (
                <span className={classes.breadcrumbs}>/ {breadcrumb}</span>
              )}
            </div>
            <div className={classes.actions}>
              <div className={classes.searchWrapper}>
                <Input
                  className={classes.search}
                  size="small"
                  contentBefore={<SearchRegular />}
                  placeholder="搜索文档…"
                  value={searchQuery}
                  onChange={(_e, d) => setSearchQuery(d.value ?? '')}
                />
                {searchOpen && searchQuery.trim() && (
                  <div className={classes.searchDropdown}>
                    {filteredFiles.length === 0 ? (
                      <div className={classes.searchEmpty}>未找到匹配文档</div>
                    ) : (
                      filteredFiles.map(f => (
                        <div
                          key={f}
                          className={classes.searchItem}
                          onMouseDown={(e) => {
                            e.preventDefault() // 阻止 blur
                            navigate(`/review?document=${encodeURIComponent(f)}`)
                            setSearchQuery('')
                          }}
                        >
                          <span className={classes.searchItemIcon}><DocumentTextRegular /></span>
                          <div>
                            <div className={classes.searchItemName}>{f}</div>
                            <div className={classes.searchItemHint}>点击审核此文档</div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
              <Button appearance="subtle" size="small" onClick={onToggleMode}>
                {mode === 'dark' ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <WeatherSunnyRegular />
                    浅色
                  </span>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <WeatherMoonRegular />
                    深色
                  </span>
                )}
              </Button>
            </div>
          </header>
          <main className={classes.page}>{children}</main>
        </div>
      </div>
    </div>
  )
}
