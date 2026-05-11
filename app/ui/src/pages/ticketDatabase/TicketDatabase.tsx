import { Text, makeStyles, tokens } from '@fluentui/react-components'
import { DatabaseRegular } from '@fluentui/react-icons'

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    height: '100%',
  },
  title: {
    fontSize: '20px',
    fontWeight: 600,
    color: tokens.colorBrandForeground1,
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    flex: 1,
    color: tokens.colorNeutralForeground3,
  },
  emptyIcon: {
    fontSize: '48px',
    color: tokens.colorNeutralForeground4,
  },
})

export default function TicketDatabase() {
  const classes = useStyles()

  return (
    <div className={classes.container}>
      <div className={classes.title}>作业票数据库</div>
      <div className={classes.empty}>
        <DatabaseRegular className={classes.emptyIcon} />
        <Text size={400}>暂无数据</Text>
        <Text size={200}>结构化作业票数据将在此展示</Text>
      </div>
    </div>
  )
}
