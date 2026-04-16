import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import SiteLayout from './components/layout/SiteLayout.jsx'
import { useLanguage } from './i18n/LanguageContext.js'

const ArticlePage = lazy(() => import('./pages/ArticlePage.jsx'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage.jsx'))
const AdminConsolePage = lazy(() => import('./pages/AdminConsolePage.jsx'))
const AdminContentOperationsPage = lazy(() => import('./pages/AdminContentOperationsPage.jsx'))
const AdminMembershipsPage = lazy(() => import('./pages/AdminMembershipsPage.jsx'))
const ChatPage = lazy(() => import('./pages/ChatPage.jsx'))
const CommercialPage = lazy(() => import('./pages/CommercialPage.jsx'))
const CommercialLeadsPage = lazy(() => import('./pages/CommercialLeadsPage.jsx'))
const ColumnPage = lazy(() => import('./pages/ColumnPage.jsx'))
const EditorialWorkbenchPage = lazy(() => import('./pages/EditorialWorkbenchPage.jsx'))
const HomePage = lazy(() => import('./pages/HomePage.jsx'))
const LoginPage = lazy(() => import('./pages/LoginPage.jsx'))
const MediaDetailPage = lazy(() => import('./pages/MediaDetailPage.jsx'))
const MediaHubPage = lazy(() => import('./pages/MediaHubPage.jsx'))
const MediaStudioPage = lazy(() => import('./pages/MediaStudioPage.jsx'))
const MembershipPage = lazy(() => import('./pages/MembershipPage.jsx'))
const MyFollowingPage = lazy(() => import('./pages/MyFollowingPage.jsx'))
const MyLibraryPage = lazy(() => import('./pages/MyLibraryPage.jsx'))
const OrganizationPage = lazy(() => import('./pages/OrganizationPage.jsx'))
const OrganizationsPage = lazy(() => import('./pages/OrganizationsPage.jsx'))
const RagAdminPage = lazy(() => import('./pages/RagAdminPage.jsx'))
const SearchPage = lazy(() => import('./pages/SearchPage.jsx'))
const TagPage = lazy(() => import('./pages/TagPage.jsx'))
const TimeMachinePage = lazy(() => import('./pages/TimeMachinePage.jsx'))
const TopicPage = lazy(() => import('./pages/TopicPage.jsx'))
const TopicsPage = lazy(() => import('./pages/TopicsPage.jsx'))
const UserKnowledgeHubPage = lazy(() => import('./pages/UserKnowledgeHubPage.jsx'))
const UserKnowledgeThemePage = lazy(() => import('./pages/UserKnowledgeThemePage.jsx'))

function PageFallback() {
  const { t } = useLanguage()
  return <div className="page-shell py-16 text-sm text-slate-500">{t('pageLoading')}</div>
}

function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/">
                <AnalyticsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requireAdmin>
                <AdminConsolePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/memberships"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <AdminMembershipsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/rag"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <RagAdminPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/content-ops"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <AdminContentOperationsPage />
              </ProtectedRoute>
            }
          />
          <Route path="/article/:id" element={<ArticlePage />} />
          <Route path="/audio/:slug" element={<MediaDetailPage kind="audio" />} />
          <Route path="/audio" element={<MediaHubPage kind="audio" />} />
          <Route path="/column/:slug" element={<ColumnPage />} />
          <Route path="/tag/:slug" element={<TagPage />} />
          <Route path="/membership" element={<MembershipPage />} />
          <Route path="/following" element={<MyFollowingPage />} />
          <Route path="/organizations" element={<OrganizationsPage />} />
          <Route path="/organization/:slug" element={<OrganizationPage />} />
          <Route path="/topic/:slug" element={<TopicPage />} />
          <Route path="/topics" element={<TopicsPage />} />
          <Route path="/time-machine" element={<TimeMachinePage />} />
          <Route
            path="/chat"
            element={
              <ProtectedRoute requireAiAssistant fallbackPath="/membership">
                <ChatPage />
              </ProtectedRoute>
            }
          />
          <Route path="/commercial" element={<CommercialPage />} />
          <Route
            path="/commercial/leads"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <CommercialLeadsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/editorial"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <EditorialWorkbenchPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/media-studio"
            element={
              <ProtectedRoute requireAdmin fallbackPath="/admin">
                <MediaStudioPage />
              </ProtectedRoute>
            }
          />
          <Route path="/me" element={<MyLibraryPage />} />
          <Route
            path="/me/knowledge"
            element={
              <ProtectedRoute requireAiAssistant fallbackPath="/membership">
                <UserKnowledgeHubPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/me/knowledge/:slug"
            element={
              <ProtectedRoute requireAiAssistant fallbackPath="/membership">
                <UserKnowledgeThemePage />
              </ProtectedRoute>
            }
          />
          <Route path="/video/:slug" element={<MediaDetailPage kind="video" />} />
          <Route path="/video" element={<MediaHubPage kind="video" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App
