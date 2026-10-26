import { AdvancedRenderer } from './studio/components/AdvancedOptions'
import Advanced from './Advanced'
import Confirm from './Confirm'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, AudioLines, Clapperboard, Compass, Contact, Film, FolderHeart, ImagePlus, Images, ListChecks, Mail, PlugZap, ScrollText, Settings2, Shield, SlidersHorizontal, Sparkles, UserRound, Users, WandSparkles, Workflow, type LucideIcon } from 'lucide-react'
import AgentView from './studio/views/AgentView'
import CreateView from './studio/views/CreateView'
import EditView, { type EditHandoff } from './studio/views/EditView'
import VideoView from './studio/views/VideoView'
import MusicView from './studio/views/MusicView'
import DirectorView from './studio/views/DirectorView'
import type { ArtifactRef } from './studio/lib/api'
import Account from './system'
import Admin from './admin'
import Providers from './Providers'
import Mcp from './Mcp'
import Lab, { type MenuGroup } from './lab/Lab'
import { api } from './bridge'
import { Empty, Modal, PageHeading } from './ui'
import { t, useLocale, type MessageKey } from './i18n'

type Nav = { path: string; title: string; icon: LucideIcon; tone: string; hint?: string }
// Titles and hints are catalog keys; brand hints (model names) stay as written.
type NavDef = Omit<Nav,'title'|'hint'> & { title: MessageKey; hint?: MessageKey; brand?: string }
const creative: NavDef[] = [ {path:'/',title:'shell.nav.explore',icon:Compass,tone:'image',hint:'shell.nav.exploreHint'}, {path:'/image',title:'shell.nav.image',icon:ImagePlus,tone:'image',brand:'Qwen Image 2.1'}, {path:'/video',title:'shell.nav.video',icon:Film,tone:'video',brand:'MiniMax H3'}, {path:'/audio',title:'shell.nav.audio',icon:AudioLines,tone:'music',brand:'YuE2 3B'}, {path:'/director',title:'shell.nav.director',icon:Clapperboard,tone:'director',hint:'shell.nav.directorHint'} ]
const advanced: NavDef[] = [ {path:'/advanced/image',title:'shell.nav.imageAdvanced',icon:ImagePlus,tone:'image',hint:'shell.nav.imageAdvancedHint'}, {path:'/edit',title:'shell.nav.editAdvanced',icon:WandSparkles,tone:'edit',hint:'shell.nav.editAdvancedHint'}, {path:'/advanced/video',title:'shell.nav.videoAdvanced',icon:Film,tone:'video',hint:'shell.nav.videoAdvancedHint'}, {path:'/advanced/music',title:'shell.nav.musicAdvanced',icon:AudioLines,tone:'music',hint:'shell.nav.musicAdvancedHint'}, {path:'/advanced/director',title:'shell.nav.directorAdvanced',icon:Clapperboard,tone:'director',hint:'shell.nav.directorAdvancedHint'}, {path:'/agent',title:'shell.nav.agent',icon:Sparkles,tone:'agent',hint:'shell.nav.agentHint'} ]
const library: NavDef[] = [{path:'/library',title:'shell.nav.library',icon:FolderHeart,tone:'library'},{path:'/gallery',title:'shell.nav.gallery',icon:Images,tone:'library',hint:'shell.nav.galleryHint'},{path:'/characters',title:'shell.nav.characters',icon:Contact,tone:'library',hint:'shell.nav.charactersHint'},{path:'/jobs',title:'shell.nav.jobs',icon:ListChecks,tone:'library'}]
const account: NavDef[] = [{path:'/account/profile',title:'shell.nav.profile',icon:UserRound,tone:'account'},{path:'/account/providers',title:'shell.nav.providers',icon:Workflow,tone:'account'},{path:'/account/mcp',title:'shell.nav.mcp',icon:PlugZap,tone:'account'},{path:'/account/preferences',title:'shell.nav.preferences',icon:SlidersHorizontal,tone:'account'},{path:'/account/security',title:'shell.nav.security',icon:Shield,tone:'account'}]
const administration: NavDef[] = [{path:'/admin/users',title:'shell.nav.users',icon:Users,tone:'account'},{path:'/admin/invitations',title:'shell.nav.invitations',icon:Mail,tone:'account'},{path:'/admin/providers',title:'shell.nav.approvedProviders',icon:Workflow,tone:'account'},{path:'/admin/mail',title:'shell.nav.mail',icon:Mail,tone:'account'},{path:'/admin/audit',title:'shell.nav.audit',icon:ScrollText,tone:'account'},{path:'/admin/system',title:'shell.nav.system',icon:Settings2,tone:'account'}]
const translate = (items: NavDef[]): Nav[] => items.map(({title,hint,brand,...n}) => ({...n,title:t(title),hint:hint ? t(hint) : brand}))

export default function Studio({ current, refresh, logout }: { current: any; refresh: () => Promise<void>; logout: () => Promise<void> }) {
 const location = useLocation(), navigate = useNavigate()
 const path = location.pathname
 const locale = useLocale()
 const groups = useMemo(() => [['studio',t('shell.group.studio'),creative],['advanced',t('shell.group.advanced'),advanced],['space',t('shell.group.space'),library],['account',t('shell.group.account'),account],...(current.role === 'admin' ? [['admin',t('shell.group.admin'),administration]] : [])].map(([id,label,items]) => [id,label,translate(items as NavDef[])]) as [string,string,Nav[]][], [current.role, locale])
 const nav = groups.flatMap(g => g[2])
 const page = nav.find(n => n.path === path)
 const menu: MenuGroup[] = groups.filter(([id]) => id !== 'studio').map(([,label,items]) => ({ label, items: items.map(({path,title}) => ({path,title})) }))
 const [visited,setVisited] = useState(new Set([path]))
 const [health,setHealth] = useState<any>(null)
 const [command,setCommand] = useState(false)
 const [search,setSearch] = useState('')
 const [edit,setEdit] = useState<EditHandoff|null>(null)
 const [video,setVideo] = useState<ArtifactRef|null>(null)
 const tone = page?.tone || 'image'
 useEffect(() => { setVisited(v => new Set([...v,path])) }, [path])
 useEffect(() => { let live = true; const load = () => void api('GET','/v1/health').then(v => {if(live) setHealth(v)}).catch(() => {if(live) setHealth(null)}); load(); const timer=setInterval(load,8000); return () => {live=false;clearInterval(timer)} }, [])
 useEffect(() => { const key = (e: KeyboardEvent) => { if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {e.preventDefault();setCommand(v=>!v)} }; window.addEventListener('keydown',key); return () => window.removeEventListener('keydown',key) }, [])
 const mounted = (p:string) => visited.has(p) || path===p
 const results = nav.filter(n=>n.title.toLowerCase().includes(search.toLowerCase()) || n.hint?.toLowerCase().includes(search.toLowerCase()))
 // Classic tools stay mounted once visited so a running job keeps its state while the user browses.
 const classic = <>
  {mounted('/agent') && <section hidden={path!=='/agent'} className="tool-screen" data-tone="agent"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:t('shell.nav.agent')})} title={t('shell.page.agentTitle')} plate="home">{t('shell.page.agentBody')}</PageHeading><Providers compact/><AgentView active={path==='/agent'}/></section>}
  {mounted('/advanced/image') && <section hidden={path!=='/advanced/image'} className="tool-screen" data-tone="image"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:'Qwen Image 2.1'})} title={t('shell.page.imageTitle')} plate="image"/><CreateView active={path==='/advanced/image'}/></section>}
  {mounted('/edit') && <section hidden={path!=='/edit'} className="tool-screen" data-tone="edit"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:t('shell.page.editName')})} title={t('shell.page.editTitle')} plate="edit"/><EditView active={path==='/edit'} incoming={edit}/></section>}
  {mounted('/advanced/video') && <section hidden={path!=='/advanced/video'} className="tool-screen" data-tone="video"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:'MiniMax H3'})} title={t('shell.page.videoTitle')} plate="video"/><VideoView incoming={video}/></section>}
  {mounted('/advanced/music') && <section hidden={path!=='/advanced/music'} className="tool-screen" data-tone="music"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:'YuE2'})} title={t('shell.page.musicTitle')} plate="music"/><MusicView/></section>}
  {mounted('/advanced/director') && <section hidden={path!=='/advanced/director'} className="tool-screen" data-tone="director"><PageHeading eyebrow={t('shell.page.advancedEyebrow',{name:t('shell.nav.director')})} title={t('shell.page.directorTitle')} plate="director"/><DirectorView/></section>}
  {path==='/account/mcp' && <Mcp current={current}/>}
  {path==='/account/providers' && <><PageHeading eyebrow={t('shell.page.providersEyebrow')} title={t('shell.nav.providers')}>{t('shell.page.providersBody')}</PageHeading><Providers/></>}
  {['/account/profile','/account/security','/account/preferences'].includes(path) && <Account key={path} section={path.split('/').at(-1)!} current={current} refresh={refresh}/>}
  {path.startsWith('/admin/') && current.role==='admin' && page && <Admin key={path} section={path.split('/').at(-1)!} current={current} refresh={refresh} health={health}/>}
  {!page && <Empty title={t('shell.notFound.title')} pose="sleep"><Link to="/">{t('shell.notFound.back')}</Link></Empty>}
 </>
 return <AdvancedRenderer.Provider value={Advanced}>
  <Lab current={current} health={health} groups={menu} onLogout={() => void logout()} classic={classic} tone={tone}/>
  <Modal open={command} onOpenChange={setCommand} title={t('shell.command.title')} description={t('shell.command.description')}><input autoFocus aria-label={t('shell.command.searchLabel')} placeholder={t('shell.command.searchPlaceholder')} value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{ if(e.key==='Enter' && results[0]) { navigate(results[0].path); setCommand(false); setSearch('') } }}/><div className="command-results">{results.map(n=><button key={n.path} data-tone={n.tone} onClick={()=>{navigate(n.path);setCommand(false);setSearch('')}}><n.icon size={18}/><span>{n.title}{n.hint && <small>{n.hint}</small>}</span><ArrowRight size={16}/></button>)}</div></Modal>
  <Confirm/>
 </AdvancedRenderer.Provider>
}
