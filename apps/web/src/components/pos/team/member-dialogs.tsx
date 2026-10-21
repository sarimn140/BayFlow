'use client'

import type { FormEvent } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { MockTeamMember } from '@/lib/mock-data'

import { RoleChoice } from './role-choice'
import { deactivateMessage, isStaffRole, roleName, type StaffRole } from './team-data'

/** Shared by the three dialogs: which member, and where focus goes when the dialog closes. */
interface MemberDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  member: MockTeamMember
  /** Puts focus back on the member's row menu (the menu item that opened the dialog is gone). */
  onCloseAutoFocus: (event: Event) => void
}

/** "Change role" (E-27 `{role}`): the four staff roles, the current one marked. */
export function ChangeRoleDialog({
  open,
  onOpenChange,
  member,
  onCloseAutoFocus,
  value,
  onValueChange,
  onConfirm,
}: MemberDialogProps & {
  value: StaffRole
  onValueChange: (role: StaffRole) => void
  onConfirm: (role: StaffRole) => void
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onConfirm(value)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Change {member.name}&apos;s role</DialogTitle>
            <DialogDescription>Bookings already assigned to them stay assigned.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <p id="change-role-label" className="text-sm font-medium text-foreground">
              New role
            </p>
            <RoleChoice
              idPrefix="change-role"
              value={value}
              onValueChange={onValueChange}
              current={isStaffRole(member.role) ? member.role : undefined}
              labelledBy="change-role-label"
            />
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Save role</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** "Deactivate" (E-27 `{is_active: false}`): a destructive confirm; focus starts on Cancel (R6). */
export function DeactivateDialog({
  open,
  onOpenChange,
  member,
  onCloseAutoFocus,
  shopName,
  openJobs,
  onConfirm,
}: MemberDialogProps & { shopName: string; openJobs: number | null; onConfirm: () => void }) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogHeader>
          <AlertDialogTitle>Deactivate {member.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            {deactivateMessage(member.name, shopName, openJobs)}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            Deactivate
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** "Reactivate" (E-27 `{is_active: true}`): a plain confirm. */
export function ReactivateDialog({
  open,
  onOpenChange,
  member,
  onCloseAutoFocus,
  shopName,
  onConfirm,
}: MemberDialogProps & { shopName: string; onConfirm: () => void }) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogHeader>
          <AlertDialogTitle>Reactivate {member.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            {member.name} can sign in to {shopName} again as a {roleName(member.role)}.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Reactivate</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
