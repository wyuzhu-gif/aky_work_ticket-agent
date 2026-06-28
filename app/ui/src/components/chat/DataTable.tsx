import {
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from '@fluentui/react-components'
import { FIELD_NAME_CN } from './FIELD_NAME_CN'
import type { QueryData } from './types'

interface DataTableProps {
  data: QueryData
}

/** 表格展示 - 翻译字段名为中文 */
export function DataTable({ data }: DataTableProps) {
  if (!data.columns.length || !data.data.length) return null

  const translatedColumns = data.columns.map(c => ({
    raw: c,
    label: FIELD_NAME_CN[c] || c,
  }))

  return (
    <Table size="small" style={{ fontSize: 12 }}>
      <TableHeader>
        <TableRow>
          {translatedColumns.map(c => (
            <TableHeaderCell key={c.raw} title={c.raw}>{c.label}</TableHeaderCell>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.data.map((row, i) => (
          <TableRow key={i}>
            {translatedColumns.map(c => (
              <TableCell key={c.raw} title={String(row[c.raw] ?? '')}>
                {String(row[c.raw] ?? '')}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
