<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const loading = ref(false)
const form = reactive({ default_sit_days: 7, default_uat_days: 5, default_pre_days: 3 })

async function load() {
  loading.value = true
  try {
    const cfg = await systemApi.getConfig()
    form.default_sit_days = cfg.default_sit_days
    form.default_uat_days = cfg.default_uat_days
    form.default_pre_days = cfg.default_pre_days
  } finally {
    loading.value = false
  }
}

async function save() {
  if (form.default_sit_days < 1 || form.default_uat_days < 1 || form.default_pre_days < 1) {
    ElMessage.error('天数至少为1')
    return
  }
  await systemApi.updateConfig({
    default_sit_days: form.default_sit_days,
    default_uat_days: form.default_uat_days,
    default_pre_days: form.default_pre_days,
  })
  ElMessage.success('已保存,新建计划时自动按此天数设置阶段时间')
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="hover" style="max-width: 560px">
      <template #header><span style="font-weight: 600">阶段默认天数配置</span></template>
      <el-form label-width="160px">
        <el-form-item label="SIT 天数">
          <el-input-number v-model="form.default_sit_days" :min="1" :max="90" :step="1" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">默认7天</span>
        </el-form-item>
        <el-form-item label="UAT 天数">
          <el-input-number v-model="form.default_uat_days" :min="1" :max="90" :step="1" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">默认5天</span>
        </el-form-item>
        <el-form-item label="预发版(PRE) 天数">
          <el-input-number v-model="form.default_pre_days" :min="1" :max="90" :step="1" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">默认3天</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="说明:新建测试计划时,自动按此天数设置各阶段起止时间(SIT结束=UAT开始,UAT结束=PRE开始)。单个计划的阶段时间可在测试计划页修改。"
      />
    </el-card>
  </div>
</template>
