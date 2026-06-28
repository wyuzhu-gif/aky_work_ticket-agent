import { Text } from '@fluentui/react-components'
import { DataUsageRegular } from '@fluentui/react-icons'
import { Chart as ChartJS, CategoryScale, LinearScale, TimeScale, BarElement, LineElement, PointElement, ArcElement, Title, Tooltip, Legend } from 'chart.js'
import { Bar, Line, Pie, Scatter } from 'react-chartjs-2'
import { useChatStyles } from './useChatStyles'

ChartJS.register(CategoryScale, LinearScale, TimeScale, BarElement, LineElement, PointElement, ArcElement, Title, Tooltip, Legend)

interface ChartDisplayProps {
  config: Record<string, unknown>
}

/** chart.js 图表渲染 */
export function ChartDisplay({ config }: ChartDisplayProps) {
  const classes = useChatStyles()
  const { type, data, options } = config as { type: string; data: any; options: any }

  if (!type || !data) return null

  // 工程级修复 (2026-06-25, per 你提示的 6 步方案):
  //   - responsive + maintainAspectRatio: false (Chart.js 自己撑满)
  //   - min-width: 0 在每一层都是关键 (flex item 默认 min-width: auto = 反向收缩)
  //   - canvas 外层 width: 100% + height: 380 + position: relative
  const chartProps = {
    data,
    options: {
      ...options,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top' as const },
        ...(options?.plugins || {}),
      },
    },
  }

  const renderChart = () => {
    switch (type) {
      case 'bar': return <Bar {...chartProps} />
      case 'line': return <Line {...chartProps} />
      case 'pie': return <Pie {...chartProps} />
      case 'scatter': return <Scatter {...chartProps} />
      default: return null
    }
  }

  return (
    <div className={classes.chartWrap}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <DataUsageRegular style={{ fontSize: 14 }} />
        <Text size={200} weight="semibold">数据可视化</Text>
      </div>
      {/* chart canvas 容器: min-width: 0 + flex: 1 + padding: 0 + width: 100% */}
      <div style={{
        width: '100%',
        minWidth: 0,           // ⭐ 关键
        flex: 1,               // ⭐ 关键 (外层 display: flex)
        padding: 0,
      }}>
        {/* canvas 容器: position: relative + width: 100% + height 380 */}
        <div style={{ position: 'relative', width: '100%', height: 380 }}>
          {renderChart()}
        </div>
      </div>
    </div>
  )
}
