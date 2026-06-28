/** 格式化时间 - 相对时间展示 (刚刚/X 分钟前/X 小时前/X 天前/M/D) */
export function fmtTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso.replace(' ', 'T'))
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin}分钟前`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `${diffH}小时前`
    const diffD = Math.floor(diffH / 24)
    if (diffD < 7) return `${diffD}天前`
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch { return '' }
}
