import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const source=path.join(root,'integrations/deepseek-harness'),output=path.join(root,'dist/deepseek-harness/bilinote-mini')
fs.mkdirSync(output,{recursive:true});fs.cpSync(source,output,{recursive:true})
const host=fs.readFileSync(path.join(output,'index.js'),'utf8').replace('__PROJECT_ROOT__',JSON.stringify(root))
fs.writeFileSync(path.join(output,'index.js'),host)
const python=path.join(root,'backend/.venv/Scripts/python.exe'),server=path.join(root,'backend/mcp_server.py')
// JSON scalars are valid YAML and safely preserve Windows paths.
const q=JSON.stringify
fs.writeFileSync(path.join(output,'cordis.patch.yml'),`- insert:
    - id: bilinote-workbench
      name: '@hyc3z/dsh-bilinote-mini'
    - id: bilinote-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: bilinote
        transport: stdio
        command: ${q(python)}
        args: [${q(server)}]
        cwd: ${q(path.join(root,'backend'))}
        env:
          PYTHONUTF8: '1'
          PYTHONIOENCODING: utf-8
        failOnStartupError: false
`)
const result=spawnSync('npm',['pack','--ignore-scripts','--pack-destination',path.dirname(output)],{cwd:output,stdio:'inherit',shell:process.platform==='win32'})
if(result.status!==0)process.exit(result.status||1)
console.log('Harness plugin:',output)
