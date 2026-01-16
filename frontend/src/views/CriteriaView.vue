<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCriteriaStore } from '@/stores/criteria'
import { useDraggable } from '@vueuse/core'
import type { Criterion, CriterionType } from '@/types'
import CriterionCard from '@/components/criteria/CriterionCard.vue'
import CriterionForm from '@/components/criteria/CriterionForm.vue'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'

const route = useRoute()
const criteriaStore = useCriteriaStore()

const projectId = computed(() => Number(route.params.id))

const showAddDialog = ref(false)
const showEditDialog = ref(false)
const showDeleteDialog = ref(false)
const selectedCriterion = ref<Criterion | null>(null)
const criterionType = ref<CriterionType>('inclusion')

onMounted(() => {
  criteriaStore.fetchCriteria(projectId.value)
})

const handleAddClick = (type: CriterionType) => {
  criterionType.value = type
  selectedCriterion.value = null
  showAddDialog.value = true
}

const handleEditClick = (criterion: Criterion) => {
  selectedCriterion.value = criterion
  criterionType.value = criterion.type
  showEditDialog.value = true
}

const handleDeleteClick = (criterion: Criterion) => {
  selectedCriterion.value = criterion
  showDeleteDialog.value = true
}

const handleSubmitAdd = async (data: { code: string; description: string; rationale?: string }) => {
  await criteriaStore.createCriterion(projectId.value, {
    type: criterionType.value,
    code: data.code,
    description: data.description,
    rationale: data.rationale,
  })
  showAddDialog.value = false
}

const handleSubmitEdit = async (data: { code: string; description: string; rationale?: string }) => {
  if (!selectedCriterion.value) return

  await criteriaStore.updateCriterion(
    projectId.value,
    selectedCriterion.value.id,
    {
      code: data.code,
      description: data.description,
      rationale: data.rationale,
    }
  )
  showEditDialog.value = false
}

const handleConfirmDelete = async () => {
  if (!selectedCriterion.value) return

  await criteriaStore.deleteCriterion(projectId.value, selectedCriterion.value.id)
  showDeleteDialog.value = false
  selectedCriterion.value = null
}
</script>

<template>
  <div class="space-y-6">
    <div class="grid gap-6 md:grid-cols-2">
      <!-- Inclusion Criteria -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-bold text-green-600">Inclusion Criteria</h2>
          <Button size="sm" @click="handleAddClick('inclusion')">
            Add
          </Button>
        </div>

        <div v-if="criteriaStore.loading" class="text-center py-8">
          <p class="text-muted-foreground">Loading...</p>
        </div>

        <div v-else-if="criteriaStore.inclusionCriteria.length === 0" class="text-center py-8">
          <p class="text-muted-foreground mb-4">No inclusion criteria yet</p>
          <Button size="sm" variant="outline" @click="handleAddClick('inclusion')">
            Add Inclusion Criterion
          </Button>
        </div>

        <div v-else class="space-y-3">
          <CriterionCard
            v-for="criterion in criteriaStore.inclusionCriteria"
            :key="criterion.id"
            :criterion="criterion"
            @edit="handleEditClick"
            @delete="handleDeleteClick"
          />
        </div>
      </div>

      <!-- Exclusion Criteria -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-bold text-red-600">Exclusion Criteria</h2>
          <Button size="sm" @click="handleAddClick('exclusion')">
            Add
          </Button>
        </div>

        <div v-if="criteriaStore.loading" class="text-center py-8">
          <p class="text-muted-foreground">Loading...</p>
        </div>

        <div v-else-if="criteriaStore.exclusionCriteria.length === 0" class="text-center py-8">
          <p class="text-muted-foreground mb-4">No exclusion criteria yet</p>
          <Button size="sm" variant="outline" @click="handleAddClick('exclusion')">
            Add Exclusion Criterion
          </Button>
        </div>

        <div v-else class="space-y-3">
          <CriterionCard
            v-for="criterion in criteriaStore.exclusionCriteria"
            :key="criterion.id"
            :criterion="criterion"
            @edit="handleEditClick"
            @delete="handleDeleteClick"
          />
        </div>
      </div>
    </div>

    <!-- Add Dialog -->
    <CriterionForm
      v-model:open="showAddDialog"
      :type="criterionType"
      @submit="handleSubmitAdd"
    />

    <!-- Edit Dialog -->
    <CriterionForm
      v-model:open="showEditDialog"
      :type="criterionType"
      :criterion="selectedCriterion || undefined"
      @submit="handleSubmitEdit"
    />

    <!-- Delete Dialog -->
    <Dialog v-model:open="showDeleteDialog" title="Delete Criterion">
      <div class="space-y-4">
        <p class="text-sm">
          Are you sure you want to delete this criterion? This action cannot be undone.
        </p>

        <div class="flex justify-end gap-3">
          <Button type="button" variant="outline" @click="showDeleteDialog = false">
            Cancel
          </Button>
          <Button variant="destructive" @click="handleConfirmDelete">
            Delete
          </Button>
        </div>
      </div>
    </Dialog>
  </div>
</template>
