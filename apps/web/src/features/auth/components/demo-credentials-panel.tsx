import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DEMO_ACCOUNTS,
  DEMO_AHMED_NOTE,
  DEMO_PASSWORD,
  DEMO_SHOP_NAME,
} from '@/content/demo-accounts'

/** Plain-text demo credentials for judges (D52, spec 09 §4.12): selectable text, nothing more. */
export function DemoCredentialsPanel() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">Demo accounts</h2>
        </CardTitle>
        <CardDescription>
          {DEMO_SHOP_NAME} team and a seeded customer. Password for all:{' '}
          <span className="font-mono font-medium text-foreground">{DEMO_PASSWORD}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Table>
          <TableCaption className="sr-only">
            Demo accounts for {DEMO_SHOP_NAME}, all with the password {DEMO_PASSWORD}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Role</TableHead>
              <TableHead scope="col">Name</TableHead>
              <TableHead scope="col">E-mail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {DEMO_ACCOUNTS.map((account) => (
              <TableRow key={account.email}>
                <TableCell className="align-top">{account.role}</TableCell>
                <TableCell className="align-top whitespace-normal">
                  {account.name}
                  {account.note ? (
                    <span className="block text-xs text-muted-foreground">{account.note}</span>
                  ) : null}
                </TableCell>
                <TableCell className="align-top font-mono text-xs select-all">
                  {account.email}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="text-sm text-muted-foreground">{DEMO_AHMED_NOTE}</p>
      </CardContent>
    </Card>
  )
}
