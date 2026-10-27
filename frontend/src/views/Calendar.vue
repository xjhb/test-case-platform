<template>
  <div class="calendar-page">
    <div class="page-header">
      <h2>测试计划日历</h2>
      <div class="header-controls">
        <el-select v-model="selectedProject" placeholder="选择项目" clearable style="width: 200px" @change="loadCalendar">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button-group>
          <el-button @click="prevMonth">
            <el-icon><ArrowLeft /></el-icon>
          </el-button>
          <el-button @click="goToday">今天</el-button>
          <el-button @click="nextMonth">
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </el-button-group>
        <span class="current-month">{{ currentYear }}年{{ currentMonth }}月</span>
      </div>
    </div>

    <div class="calendar-container">
      <div class="calendar-grid">
        <div class="calendar-header">
          <div class="weekday" v-for="day in weekdays" :key="day">{{ day }}</div>
        </div>
        <div class="calendar-body">
          <div
            v-for="(day, index) in calendarDays"
            :key="index"
            class="calendar-day"
            :class="{ 'other-month': !day.currentMonth, 'today': day.isToday }"
          >
            <div class="day-number">{{ day.date }}</div>
            <div class="day-events">
              <div
                v-for="event in day.events"
                :key="event.id + event.stage"
                class="calendar-event"
                :class="'stage-' + event.stage.toLowerCase()"
                @click="showPlanDetail(event)"
              >
                <span class="event-stage">{{ event.stage }}</span>
                <span class="event-title">{{ event.version }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="detailVisible" title="计划详情" width="500px">
      <el-descriptions v-if="selectedPlan" :column="2" border>
        <el-descriptions-item label="项目">{{ selectedPlan.project_name }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ selectedPlan.version }}</el-descriptions-item>
        <el-descriptions-item label="阶段">
          <el-tag :type="stageTagType(selectedPlan.stage)">{{ selectedPlan.stage }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">{{ selectedPlan.status }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ selectedPlan.start }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ selectedPlan.end }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="goToPlan(selectedPlan)">查看计划</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { planApi, projectApi } from '../api'

const router = useRouter()
const projects = ref([])
const selectedProject = ref(null)
const currentYear = ref(new Date().getFullYear())
const currentMonth = ref(new Date().getMonth() + 1)
const calendarData = ref([])
const detailVisible = ref(false)
const selectedPlan = ref(null)

const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const stageTagType = (stage) => {
  const map = { SIT: 'primary', UAT: 'success', PRE: 'warning' }
  return map[stage] || 'info'
}

const calendarDays = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value
  const firstDay = new Date(year, month - 1, 1)
  const lastDay = new Date(year, month, 0)
  const daysInMonth = lastDay.getDate()
  const startWeekday = firstDay.getDay()

  const days = []
  const today = new Date()
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() + 1 === month

  for (let i = 0; i < startWeekday; i++) {
    const prevMonthLastDay = new Date(year, month - 1, 0)
    const date = prevMonthLastDay.getDate() - startWeekday + 1 + i
    days.push({
      date,
      currentMonth: false,
      isToday: false,
      events: [],
    })
  }

  for (let i = 1; i <= daysInMonth; i++) {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(i).padStart(2, '0')}`
    const dayEvents = calendarData.value.filter(event => {
      const start = event.start.split(' ')[0]
      const end = event.end.split(' ')[0]
      return dateStr >= start && dateStr <= end
    })

    days.push({
      date: i,
      currentMonth: true,
      isToday: isCurrentMonth && today.getDate() === i,
      events: dayEvents,
    })
  }

  const remaining = 42 - days.length
  for (let i = 1; i <= remaining; i++) {
    days.push({
      date: i,
      currentMonth: false,
      isToday: false,
      events: [],
    })
  }

  return days
})

async function loadProjects() {
  try {
    projects.value = await projectApi.list()
  } catch (e) {
    console.error(e)
  }
}

async function loadCalendar() {
  try {
    const params = {
      year: currentYear.value,
      month: currentMonth.value,
    }
    if (selectedProject.value) {
      params.project_id = selectedProject.value
    }
    calendarData.value = await planApi.calendar(params)
  } catch (e) {
    console.error(e)
  }
}

function prevMonth() {
  if (currentMonth.value === 1) {
    currentMonth.value = 12
    currentYear.value--
  } else {
    currentMonth.value--
  }
  loadCalendar()
}

function nextMonth() {
  if (currentMonth.value === 12) {
    currentMonth.value = 1
    currentYear.value++
  } else {
    currentMonth.value++
  }
  loadCalendar()
}

function goToday() {
  const today = new Date()
  currentYear.value = today.getFullYear()
  currentMonth.value = today.getMonth() + 1
  loadCalendar()
}

function showPlanDetail(plan) {
  selectedPlan.value = plan
  detailVisible.value = true
}

function goToPlan(plan) {
  router.push(`/plans?project_id=${plan.project_id}`)
}

onMounted(() => {
  loadProjects()
  loadCalendar()
})
</script>

<style scoped>
.calendar-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.current-month {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.calendar-container {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.calendar-grid {
  display: flex;
  flex-direction: column;
}

.calendar-header {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 8px;
}

.weekday {
  text-align: center;
  font-weight: 600;
  color: #606266;
  padding: 12px 0;
  background: #f5f7fa;
}

.calendar-body {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: #e4e7ed;
}

.calendar-day {
  background: #fff;
  min-height: 120px;
  padding: 8px;
  position: relative;
}

.calendar-day.other-month {
  background: #fafafa;
}

.calendar-day.other-month .day-number {
  color: #c0c4cc;
}

.calendar-day.today {
  background: #ecf5ff;
}

.day-number {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.day-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.calendar-event {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.calendar-event:hover {
  transform: translateX(2px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.calendar-event.stage-sit {
  background: #e1f3d8;
  border-left: 3px solid #67c23a;
}

.calendar-event.stage-uat {
  background: #d4e9f7;
  border-left: 3px solid #409eff;
}

.calendar-event.stage-pre {
  background: #fae3d1;
  border-left: 3px solid #e6a23c;
}

.event-stage {
  font-weight: 600;
  color: #606266;
}

.event-title {
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
