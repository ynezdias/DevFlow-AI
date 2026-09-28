import {test,expect} from '@playwright/test'
test('real dashboard connects to API',async({page})=>{
 await page.goto('/')
 await expect(page.getByRole('heading',{name:'Code Review Dashboard'})).toBeVisible()
 await expect(page.getByRole('region',{name:'Review counts'})).toBeVisible()
 await expect(page.getByRole('alert')).toHaveCount(0)
})
test('history, partial findings, polling and hostile text',async({page})=>{
 const id='11111111-1111-1111-1111-111111111111'
 let calls=0
 const finding={file_path:'auth.py',line_number:2,source:'bandit',severity:'high',category:'B605',title:'Unsafe shell',description:'<script>window.PWNED=true</script>',suggestion:'Use an argument list.'}
 const review={id,repository_name:'test/repo',pull_request_number:7,head_sha:'a'.repeat(40),status:'failed',created_at:new Date().toISOString(),started_at:null,completed_at:null,error_code:'analysis_incomplete',publication_status:'published',github_check_run_id:null,finding_count:1,scope_summary:{limited:false,report:{status:'failed',summary:{total_findings:1},analysis:{static_analysis:'completed',ai_analysis:'failed'},findings:[finding]}}}
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname
  let body:unknown
  if(path.endsWith('/metrics/summary'))body={total_reviews:1,failed:1,processing:0,completed:0,queued:0,superseded:0}
  else if(path.endsWith('/findings'))body=[finding]
  else if(path.endsWith(id)){calls++;body=review}
  else body={items:[review],total:1,page:1,page_size:12}
  await route.fulfill({json:body})
 })
 await page.goto('/')
 await page.getByRole('link',{name:/test\/repo/}).click()
 await expect(page.getByRole('heading',{name:'1 validated findings'})).toBeVisible()
 await expect(page.getByText('Review incomplete:',{exact:false})).toBeVisible()
 await expect(page.getByText(finding.description,{exact:true})).toBeVisible()
 await expect(page.getByText('Use an argument list.')).toBeVisible()
 expect(await page.evaluate(()=>Object.hasOwn(window,'PWNED'))).toBe(false)
 await expect.poll(()=>calls,{timeout:8000}).toBeGreaterThan(1)
 await page.getByRole('link',{name:'? Review history'}).click()
 await expect(page.getByRole('heading',{name:'Recent reviews'})).toBeVisible()
})
test('API error is visible',async({page})=>{
 await page.route('**/api/**',route=>route.fulfill({status:503,json:{}}))
 await page.goto('/')
 await expect(page.getByRole('alert')).toContainText('503')
})
