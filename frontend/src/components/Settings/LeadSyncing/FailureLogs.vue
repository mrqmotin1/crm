<template>
  <div v-if="selectedLog">
    <div class="flex justify-between items-center">
      <Button
        variant="ghost"
        icon-left="lucide-chevron-left"
        @click="selectedLog = null"
      >
        {{ __('Back to All Logs') }}
      </Button>
      <Button
        v-if="logDoc?.document?.retrySync && selectedLog.type != 'Synced'"
        :loading="logDoc?.document?.retrySync.loading"
        @click="logDoc?.document?.retrySync.submit()"
      >
        {{ __('Retry Sync') }}
      </Button>
    </div>

    <div class="grid grid-cols-2 gap-2 mt-4">
      <FormControl
        type="text"
        :label="__('Log ID')"
        :value="selectedLog.name"
        disabled
      />

      <FormControl
        type="text"
        :label="__('Reason')"
        :value="selectedLog.type"
        disabled
      />
    </div>

    <div class="mt-4 flex flex-col gap-8">
      <div>
        <Textarea
          class="h-[250px]"
          :label="__('Lead Data')"
          :value="selectedLog.lead_data"
          disabled
        />
      </div>

      <div>
        <Textarea
          v-if="selectedLog.traceback"
          class="h-[250px]"
          :label="__('Traceback')"
          disabled
          :value="selectedLog.traceback"
        />
      </div>
    </div>
  </div>

  <div v-if="!selectedLog" class="mb-3 flex flex-col gap-2">
    <div class="flex items-center justify-between gap-2">
      <span class="text-sm text-ink-gray-6">
        {{
          __(
            'Retry every failed submission once: duplicates are merged into the existing lead when merging is on.',
          )
        }}
      </span>
      <Button
        :label="retryPreview ? __('Check again') : __('Retry all')"
        :loading="retryAll.loading && retryAll.params?.dry_run"
        @click="retryAll.submit({ source: props.source, dry_run: 1 })"
      />
    </div>
    <div
      v-if="retryPreview"
      class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-8"
    >
      <div class="font-medium">
        {{
          retryPreview.dry_run
            ? __('What a retry would do')
            : __('Retry finished')
        }}
      </div>
      <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-ink-gray-7">
        <span v-for="(value, key) in retryPreview.summary" :key="key">
          {{ summaryLabels[key] || key }}: <b>{{ value }}</b>
        </span>
      </div>
      <ul class="mt-2 max-h-40 overflow-auto">
        <li v-for="r in retryPreview.results" :key="r.log" class="py-0.5">
          <Badge :label="resultLabels[r.result] || r.result" />
          <span class="ml-2">{{ r.meta_id }}</span>
          <span v-if="r.lead" class="ml-1">→ {{ r.lead }}</span>
          <span v-if="r.action" class="ml-1 text-ink-gray-5"
            >({{ actionLabels[r.action] || r.action }})</span
          >
          <span
            v-if="r.note || r.error || r.skipped"
            class="ml-1 text-ink-gray-5"
            >{{ r.note || r.error || r.skipped }}</span
          >
        </li>
      </ul>
      <div v-if="retryPreview.dry_run" class="mt-3 flex gap-2">
        <Button
          variant="solid"
          :label="__('Apply')"
          :loading="retryAll.loading && !retryAll.params?.dry_run"
          @click="retryAll.submit({ source: props.source, dry_run: 0 })"
        />
        <Button
          variant="ghost"
          :label="__('Cancel')"
          @click="retryPreview = null"
        />
      </div>
    </div>
  </div>

  <ListView
    v-if="!selectedLog && failedLeadSyncLogList?.data"
    class="h-full"
    :columns="columns"
    :rows="failedLeadSyncLogList?.data"
    :options="{
      selectable: false,
      showTooltip: true,
      resizeColumn: false,
      emptyState: {
        title: __('No Failure Logs Found'),
        description: __('Any failed lead syncs will show up here'),
      },
      onRowClick: (row) => {
        selectedLog = row
      },
    }"
  >
    <template #cell="{ item, column }">
      <Badge v-if="column.key === 'type'">{{ item }}</Badge>
      <span v-else class="text-base">{{ item }}</span>
    </template>
  </ListView>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useDocument } from '@/data/document'
import {
  Badge,
  Button,
  createResource,
  createListResource,
  Textarea,
  ListView,
  FormControl,
  toast,
} from 'frappe-ui'

const props = defineProps({
  source: { type: String, required: true },
})

const selectedLog = ref(null)

const failedLeadSyncLogList = createListResource({
  doctype: 'Failed Lead Sync Log',
  fields: ['name', 'type', 'lead_data', 'traceback'],
  filters: {
    source: props.source,
  },
  auto: true,
})

const retryPreview = ref(null)
const retryAll = createResource({
  url: 'crm.lead_syncing.merge.retry_failed',
  onSuccess(data) {
    retryPreview.value = data
    if (!data.dry_run) {
      toast.success(__('Retry finished'))
      failedLeadSyncLogList.reload()
    }
  },
  onError(e) {
    toast.error(e.messages?.[0] || __('Error retrying failed leads'))
  },
})
const summaryLabels = {
  logs: __('Logs'),
  submissions: __('Submissions'),
  merged: __('Merged'),
  inserted: __('New leads'),
  already_in_crm: __('Already in CRM'),
  conflicts: __('Conflicts'),
  failed: __('Failed'),
  repeats: __('Repeat logs'),
}
const resultLabels = {
  merged: __('Merge'),
  inserted: __('New lead'),
  already_in_crm: __('Already in CRM'),
  conflicts: __('Conflict'),
  failed: __('Failed'),
}
const actionLabels = {
  reopened: __('comes back to New'),
  alerted: __('status kept, owner gets a task'),
  restarted: __('still New, follow-up restarts'),
  kept: __('status kept: changed after the submission'),
  updated: __('blank fields and a note'),
}

const columns = [
  {
    label: __('ID'),
    key: 'name',
  },
  {
    label: __('Type'),
    key: 'type',
  },
]

const logDoc = ref(null)
watch(selectedLog, () => {
  if (!selectedLog.value?.name) {
    return
  }

  logDoc.value = useDocument('Failed Lead Sync Log', selectedLog.value.name, {
    whitelistedMethods: {
      retrySync: {
        method: 'retry_sync',
        onSuccess() {
          toast.success(__('Sync successful!'))
        },
        onError(e) {
          toast.error(
            e.message ||
              (e.messages ?? e.messages[0]) ||
              e.exc_type ||
              __('Error syncing lead'),
          )
        },
      },
    },
  })
})
</script>
