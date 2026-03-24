param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$Target
)

$ErrorActionPreference = "Stop"

$wdStatisticPages = 2
$wdInformationPage = 3
$wdCollapseEnd = 0

function Get-ParagraphText {
    param([object]$Paragraph)

    if (-not $Paragraph) {
        return ""
    }

    $text = [string]$Paragraph.Range.Text
    $text = $text -replace [regex]::Escape([string][char]13), ""
    $text = $text -replace [regex]::Escape([string][char]7), ""
    $text = $text -replace [regex]::Escape([string][char]11), ""
    return $text.Trim()
}

function Get-AllParagraphs {
    param([object]$Document)

    $items = @()
    for ($i = 1; $i -le $Document.Paragraphs.Count; $i++) {
        $items += $Document.Paragraphs.Item($i)
    }
    return $items
}

function Find-Paragraph {
    param(
        [object]$Document,
        [string]$Text,
        [int]$Occurrence = 1,
        [int]$AfterStart = -1
    )

    $count = 0
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ($para.Range.Start -le $AfterStart) {
            continue
        }
        if ((Get-ParagraphText -Paragraph $para) -eq $Text) {
            $count++
            if ($count -eq $Occurrence) {
                return $para
            }
        }
    }
    return $null
}

function Find-NextParagraph {
    param(
        [object]$Document,
        [string]$Text,
        [int]$AfterStart
    )

    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ($para.Range.Start -le $AfterStart) {
            continue
        }
        if ((Get-ParagraphText -Paragraph $para) -eq $Text) {
            return $para
        }
    }
    return $null
}

function Get-StyleName {
    param([object]$Paragraph)

    try {
        return [string]$Paragraph.Range.Style.NameLocal
    } catch {
        try {
            return [string]$Paragraph.Style
        } catch {
            return ""
        }
    }
}

function Find-ParagraphByStyleAndText {
    param(
        [object]$Document,
        [string]$StyleName,
        [string]$Text
    )

    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ((Get-StyleName -Paragraph $para) -eq $StyleName -and (Get-ParagraphText -Paragraph $para) -eq $Text) {
            return $para
        }
    }
    return $null
}

function Set-ParagraphText {
    param(
        [object]$Document,
        [string]$OldText,
        [string]$NewText,
        [int]$Occurrence = 1,
        [object]$Style = $null
    )

    $para = Find-Paragraph -Document $Document -Text $OldText -Occurrence $Occurrence
    if (-not $para) {
        throw "Paragraph not found: $OldText"
    }
    $para.Range.Text = $NewText + [char]13
    if ($Style) {
        $para.Range.Style = $Style
    }
    return $para
}

function Set-ParagraphStyle {
    param(
        [object]$Document,
        [string]$Text,
        [object]$Style,
        [int]$Occurrence = 1
    )

    $para = Find-Paragraph -Document $Document -Text $Text -Occurrence $Occurrence
    if (-not $para) {
        throw "Paragraph not found for style update: $Text"
    }
    $para.Range.Style = $Style
    return $para
}

function Delete-HeadingOnly {
    param(
        [object]$Document,
        [string]$Text,
        [int]$Occurrence = 1
    )

    $para = Find-Paragraph -Document $Document -Text $Text -Occurrence $Occurrence
    if ($para) {
        $para.Range.Delete()
    }
}

function Delete-Section {
    param(
        [object]$Document,
        [string]$StartText,
        [string]$NextText,
        [int]$StartOccurrence = 1
    )

    $start = Find-Paragraph -Document $Document -Text $StartText -Occurrence $StartOccurrence
    if (-not $start) {
        throw "Delete-Section start not found: $StartText"
    }
    $next = Find-NextParagraph -Document $Document -Text $NextText -AfterStart $start.Range.Start
    if (-not $next) {
        throw "Delete-Section next not found: $NextText"
    }
    $range = $Document.Range($start.Range.Start, $next.Range.Start)
    $range.Delete()
}

function Move-SectionBefore {
    param(
        [object]$Document,
        [string]$StartText,
        [string]$NextText,
        [string]$BeforeText
    )

    $start = Find-Paragraph -Document $Document -Text $StartText
    if (-not $start) {
        throw "Move-SectionBefore start not found: $StartText"
    }
    $next = Find-NextParagraph -Document $Document -Text $NextText -AfterStart $start.Range.Start
    if (-not $next) {
        throw "Move-SectionBefore next not found: $NextText"
    }
    $before = Find-Paragraph -Document $Document -Text $BeforeText
    if (-not $before) {
        throw "Move-SectionBefore target not found: $BeforeText"
    }

    $text = $Document.Range($start.Range.Start, $next.Range.Start).FormattedText
    $Document.Range($start.Range.Start, $next.Range.Start).Delete()
    $before = Find-Paragraph -Document $Document -Text $BeforeText
    $insertRange = $before.Range.Duplicate
    $insertRange.Collapse(1)
    $insertRange.FormattedText = $text
}

function Trim-SectionText {
    param(
        [object]$Document,
        [string]$HeadingText,
        [int]$KeepParagraphCount
    )

    $heading = Find-Paragraph -Document $Document -Text $HeadingText
    if (-not $heading) {
        throw "Trim-SectionText heading not found: $HeadingText"
    }

    $nextHeadingStart = $Document.Content.End
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ($para.Range.Start -le $heading.Range.Start) {
            continue
        }
        $text = Get-ParagraphText -Paragraph $para
        if (-not $text) {
            continue
        }
        if ((Get-StyleName -Paragraph $para).ToLower().StartsWith("heading")) {
            $nextHeadingStart = $para.Range.Start
            break
        }
    }

    $kept = 0
    $deleteStart = $null
    $deleteEnd = $null
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ($para.Range.Start -le $heading.Range.Start -or $para.Range.Start -ge $nextHeadingStart) {
            continue
        }
        $text = Get-ParagraphText -Paragraph $para
        if (-not $text) {
            continue
        }
        if ($para.Range.InlineShapes.Count -gt 0) {
            continue
        }
        if ($para.Range.Tables.Count -gt 0) {
            continue
        }
        $kept++
        if ($kept -gt $KeepParagraphCount) {
            if (-not $deleteStart) {
                $deleteStart = $para.Range.Start
            }
            $deleteEnd = $para.Range.End
        }
    }

    if ($deleteStart -and $deleteEnd -and $deleteEnd -gt $deleteStart) {
        $Document.Range($deleteStart, $deleteEnd).Delete()
    }
}

function Get-BodyHeadings {
    param([object]$Document)

    $items = @()
    $started = $false
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        $text = Get-ParagraphText -Paragraph $para
        if (-not $text) {
            continue
        }
        $style = Get-StyleName -Paragraph $para
        $styleLower = $style.ToLower()
        if ($text -eq "绪论") {
            $started = $true
        }
        if (-not $started) {
            continue
        }
        if (-not $styleLower.StartsWith("heading")) {
            continue
        }
        $level = 9
        if ($styleLower -match "heading 1") { $level = 1 }
        elseif ($styleLower -match "heading 2") { $level = 2 }
        elseif ($styleLower -match "heading 3") { $level = 3 }
        else { continue }
        $list = ""
        try { $list = [string]$para.Range.ListFormat.ListString } catch {}
        $page = [int]$para.Range.Information($wdInformationPage)
        $items += [PSCustomObject]@{
            Paragraph = $para
            Level = $level
            Text = $text
            Number = $list
            Page = $page
        }
    }
    return $items
}

function Rebuild-ManualToc {
    param(
        [object]$Document,
        [object]$Toc1Style,
        [object]$Toc2Style,
        [object]$Toc3Style
    )

    $tocTitle = Find-Paragraph -Document $Document -Text "目  录"
    $firstHeading = Find-Paragraph -Document $Document -Text "绪论"
    if (-not $tocTitle -or -not $firstHeading) {
        throw "TOC anchors not found"
    }

    if ($tocTitle.Range.End -lt $firstHeading.Range.Start) {
        $Document.Range($tocTitle.Range.End, $firstHeading.Range.Start).Delete()
    }

    $Document.Repaginate()

    $selected = @(
        "绪论",
        "选题背景",
        "国内外研究现状",
        "国内研究现状",
        "国外研究现状",
        "研究内容和意义",
        "本文结构",
        "开发工具及相关技术简介",
        "开发环境与工具",
        "前端开发技术",
        "后端开发技术",
        "数据存储与数据库技术",
        "大语言模型接入与检索增强生成技术",
        "OCR与语音识别技术",
        "本章小结",
        "系统分析",
        "可行性分析",
        "技术可行性",
        "经济可行性",
        "运行可行性",
        "系统需求分析",
        "用户角色分析",
        "功能需求分析",
        "非功能需求分析",
        "业务流程分析",
        "智能对话与知识问答流程",
        "智能审单与风险处理流程",
        "数据决策与内容生成流程",
        "本章小结",
        "系统设计",
        "总体设计",
        "系统总体架构设计",
        "功能模块划分设计",
        "数据库设计",
        "数据库逻辑结构设计",
        "主要数据表设计",
        "核心模块设计",
        "对话与上下文管理模块设计",
        "文档检索与知识库模块设计",
        "OCR与语音处理模块设计",
        "特色业务模块设计",
        "智能审单模块设计",
        "决策分析与智能写作模块设计",
        "本章小结",
        "系统实现",
        "系统总体功能介绍",
        "智能对话与知识问答模块实现",
        "OCR识别、语音处理与智能审单模块实现",
        "数据决策与智能创作模块实现",
        "用户权限与系统管理模块实现",
        "本章小结",
        "系统测试",
        "测试环境与测试方法",
        "功能测试",
        "性能测试",
        "测试结果分析",
        "本章小结",
        "总结与展望",
        "总结",
        "展望",
        "参考文献",
        "致  谢"
    )

    $picked = @()
    $seen = @{}
    foreach ($item in (Get-BodyHeadings -Document $Document)) {
        $key = $item.Text
        if (-not $selected.Contains($key)) {
            continue
        }
        $count = 0
        if ($seen.ContainsKey($key)) {
            $count = [int]$seen[$key]
        }
        $count++
        $seen[$key] = $count

        if ($key -eq "本章小结" -and $count -gt 5) {
            continue
        }

        $picked += $item
    }

    $lines = @()
    foreach ($item in $picked) {
        $label = $item.Text
        if ($item.Number) {
            $label = "$($item.Number) $label"
        }
        $lines += [PSCustomObject]@{
            Text = "$label`t$($item.Page)"
            Level = $item.Level
        }
    }

    $insertRange = $Document.Range($tocTitle.Range.End, $tocTitle.Range.End)
    $buffer = ($lines | ForEach-Object { $_.Text }) -join [char]13
    if ($buffer) {
        $insertRange.InsertAfter([char]13 + $buffer + [char]13)
    }

    $firstHeading = Find-Paragraph -Document $Document -Text "绪论"
    $tocParas = @()
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ($para.Range.Start -le $tocTitle.Range.Start) {
            continue
        }
        if ($para.Range.Start -ge $firstHeading.Range.Start) {
            break
        }
        $text = Get-ParagraphText -Paragraph $para
        if ($text) {
            $tocParas += $para
        }
    }

    $lineIndex = 0
    foreach ($para in $tocParas) {
        if ($lineIndex -ge $lines.Count) {
            break
        }
        switch ($lines[$lineIndex].Level) {
            1 { $para.Range.Style = $Toc1Style }
            2 { $para.Range.Style = $Toc2Style }
            3 { $para.Range.Style = $Toc3Style }
        }
        $lineIndex++
    }
}

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Source file not found: $Source"
}

$targetDir = Split-Path -Parent $Target
if ($targetDir -and -not (Test-Path -LiteralPath $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}

Copy-Item -LiteralPath $Source -Destination $Target -Force

$word = $null
$doc = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open($Target, $false, $false)

    $heading1Style = (Find-Paragraph -Document $doc -Text "绪论").Range.Style
    $heading2Style = (Find-Paragraph -Document $doc -Text "选题背景").Range.Style
    $heading3Style = (Find-Paragraph -Document $doc -Text "国内研究现状").Range.Style
    $toc1Style = (Find-ParagraphByStyleAndText -Document $doc -StyleName "toc 1" -Text "1 绪论 ............................................................ 1").Range.Style
    $toc2Style = (Find-ParagraphByStyleAndText -Document $doc -StyleName "toc 2" -Text "1.1 选题背景 ...................................................... 1").Range.Style
    $toc3Style = (Find-ParagraphByStyleAndText -Document $doc -StyleName "toc 3" -Text "1.2.1 国内研究现状 ................................................. 2").Range.Style

    Write-Output "[1/7] Rename chapter headings"
    Set-ParagraphText -Document $doc -OldText "系统开发环境与工具选择" -NewText "开发环境与工具" | Out-Null
    Set-ParagraphText -Document $doc -OldText "前端界面构建与交互实现技术" -NewText "前端开发技术" | Out-Null
    Set-ParagraphText -Document $doc -OldText "后端服务框架与接口组织技术" -NewText "后端开发技术" | Out-Null
    Set-ParagraphText -Document $doc -OldText "数据持久化、对象存储与会话管理技术" -NewText "数据存储与数据库技术" | Out-Null
    Set-ParagraphText -Document $doc -OldText "OCR、语音与多模态处理技术" -NewText "OCR与语音识别技术" | Out-Null

    Write-Output "[2/7] Merge chapter 3"
    Delete-Section -Document $doc -StartText "场景问题与建设目标分析" -NextText "可行性分析"
    Set-ParagraphText -Document $doc -OldText "技术可行性分析" -NewText "技术可行性" | Out-Null
    Set-ParagraphText -Document $doc -OldText "经济可行性分析" -NewText "经济可行性" | Out-Null
    Set-ParagraphText -Document $doc -OldText "运行可行性分析" -NewText "运行可行性" | Out-Null
    Set-ParagraphText -Document $doc -OldText "用户角色与业务场景分析" -NewText "系统需求分析" | Out-Null
    Delete-Section -Document $doc -StartText "核心业务场景分析" -NextText "功能需求分析"
    Delete-HeadingOnly -Document $doc -Text "功能需求分析"
    Set-ParagraphText -Document $doc -OldText "智能对话与知识服务需求" -NewText "功能需求分析" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "数据查询与经营分析需求"
    Delete-HeadingOnly -Document $doc -Text "OCR、文档解析与会议纪要需求"
    Delete-HeadingOnly -Document $doc -Text "智能审单与内容生成需求"
    Delete-HeadingOnly -Document $doc -Text "管理后台与共享协同需求"
    Set-ParagraphText -Document $doc -OldText "业务流程与数据流程分析" -NewText "业务流程分析" | Out-Null
    Set-ParagraphText -Document $doc -OldText "文档知识处理流程分析" -NewText "智能对话与知识问答流程" | Out-Null
    Set-ParagraphText -Document $doc -OldText "会议音频处理流程分析" -NewText "数据决策与内容生成流程" | Out-Null
    Set-ParagraphText -Document $doc -OldText "数据问答与审单处理流程分析" -NewText "智能审单与风险处理流程" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "非功能需求分析"
    Set-ParagraphText -Document $doc -OldText "性能需求" -NewText "非功能需求分析" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "安全需求"
    Delete-HeadingOnly -Document $doc -Text "可维护性与可扩展性需求"
    Delete-HeadingOnly -Document $doc -Text "易用性与部署适应性需求"

    Write-Output "[3/7] Merge chapter 4"
    Delete-Section -Document $doc -StartText "设计目标与原则" -NextText "系统总体架构设计"
    Delete-Section -Document $doc -StartText "前端系统设计" -NextText "后端系统设计"
    Move-SectionBefore -Document $doc -StartText "数据与存储设计" -NextText "关键模块设计" -BeforeText "后端系统设计"
    Delete-Section -Document $doc -StartText "接口与安全机制设计" -NextText "本章小结"
    Set-ParagraphText -Document $doc -OldText "系统总体架构设计" -NewText "总体设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "分层总体架构设计" -NewText "系统总体架构设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "功能模块架构设计" -NewText "功能模块划分设计" | Out-Null
    Delete-Section -Document $doc -StartText "部署与运行架构设计" -NextText "数据与存储设计"
    Set-ParagraphText -Document $doc -OldText "数据与存储设计" -NewText "数据库设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "业务数据库与角色权限数据设计" -NewText "数据库逻辑结构设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "会话历史、分享与知识库数据设计" -NewText "主要数据表设计" | Out-Null
    Delete-Section -Document $doc -StartText "对象存储与运行时文件设计" -NextText "后端系统设计"
    Set-ParagraphText -Document $doc -OldText "后端系统设计" -NewText "核心模块设计" | Out-Null
    Delete-Section -Document $doc -StartText "路由装配与接口分层设计" -NextText "模式路由与上下文管理设计"
    Set-ParagraphText -Document $doc -OldText "模式路由与上下文管理设计" -NewText "对话与上下文管理模块设计" | Out-Null
    Delete-Section -Document $doc -StartText "异步任务与后台处理设计" -NextText "关键模块设计"
    Set-ParagraphText -Document $doc -OldText "关键模块设计" -NewText "特色业务模块设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "文档检索增强问答模块设计" -NewText "文档检索与知识库模块设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "OCR 与会议纪要模块设计" -NewText "OCR与语音处理模块设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "审单、报告与 PPT 生成模块设计" -NewText "智能审单模块设计" | Out-Null
    Set-ParagraphText -Document $doc -OldText "数据库智能问答模块设计" -NewText "决策分析与智能写作模块设计" | Out-Null

    Write-Output "[4/7] Merge chapter 5"
    Set-ParagraphText -Document $doc -OldText "系统实现概述" -NewText "系统总体功能介绍" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "前端核心功能实现"
    Delete-HeadingOnly -Document $doc -Text "后端核心服务实现"
    Delete-HeadingOnly -Document $doc -Text "智能能力模块实现"
    Delete-Section -Document $doc -StartText "登录认证与用户会话实现" -NextText "统一工作台与多模式交互实现"
    Set-ParagraphText -Document $doc -OldText "统一工作台与多模式交互实现" -NewText "智能对话与知识问答模块实现" -Style $heading2Style | Out-Null
    Delete-Section -Document $doc -StartText "文件上传、OCR 与会议纪要前端实现" -NextText "写作中心、分享与后台界面实现"
    Delete-Section -Document $doc -StartText "写作中心、分享与后台界面实现" -NextText "应用启动、路由装配与中间件实现"
    Delete-Section -Document $doc -StartText "应用启动、路由装配与中间件实现" -NextText "聊天服务与上下文编排实现"
    Delete-HeadingOnly -Document $doc -Text "聊天服务与上下文编排实现"
    Delete-HeadingOnly -Document $doc -Text "历史会话、分享与认证接口实现"
    Delete-Section -Document $doc -StartText "文档解析与检索增强问答实现" -NextText "数据库智能问答实现"
    Delete-Section -Document $doc -StartText "数据库智能问答实现" -NextText "OCR 与会议音频处理实现"
    Set-ParagraphText -Document $doc -OldText "OCR 与会议音频处理实现" -NewText "OCR识别、语音处理与智能审单模块实现" -Style $heading2Style | Out-Null
    Delete-HeadingOnly -Document $doc -Text "智能审单流程实现"
    Set-ParagraphText -Document $doc -OldText "报告、邮件与 PPT 生成实现" -NewText "数据决策与智能创作模块实现" -Style $heading2Style | Out-Null
    Set-ParagraphText -Document $doc -OldText "管理与运行支撑实现" -NewText "用户权限与系统管理模块实现" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "角色治理与后台管理实现"
    Delete-HeadingOnly -Document $doc -Text "运行时资源、安全机制与可维护性实现"

    Write-Output "[5/7] Merge chapter 6"
    Set-ParagraphText -Document $doc -OldText "系统测试与分析" -NewText "系统测试" | Out-Null
    Set-ParagraphText -Document $doc -OldText "测试目标与测试环境" -NewText "测试环境与测试方法" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "测试目标"
    Delete-HeadingOnly -Document $doc -Text "测试环境"
    Delete-HeadingOnly -Document $doc -Text "测试方法与评价指标"
    Delete-HeadingOnly -Document $doc -Text "登录认证与会话管理功能测试"
    Delete-HeadingOnly -Document $doc -Text "智能对话、知识库与数据库问答功能测试"
    Delete-HeadingOnly -Document $doc -Text "OCR 与会议纪要功能测试"
    Delete-HeadingOnly -Document $doc -Text "审单、写作与 PPT 生成功能测试"
    Delete-HeadingOnly -Document $doc -Text "分享协同与后台管理功能测试"
    Set-ParagraphText -Document $doc -OldText "非功能测试" -NewText "性能测试" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "性能与响应测试"
    Delete-HeadingOnly -Document $doc -Text "安全与权限控制测试"
    Delete-HeadingOnly -Document $doc -Text "稳定性与异常恢复测试"
    Delete-HeadingOnly -Document $doc -Text "兼容性与易用性测试"
    Set-ParagraphText -Document $doc -OldText "测试结果分析与效果验证" -NewText "测试结果分析" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "测试结果综合分析"
    Delete-HeadingOnly -Document $doc -Text "系统应用价值验证"
    Delete-HeadingOnly -Document $doc -Text "存在的问题与改进方向"

    Write-Output "[6/7] Merge chapter 7"
    Set-ParagraphText -Document $doc -OldText "全文工作总结" -NewText "总结" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "研究背景与目标回顾"
    Delete-HeadingOnly -Document $doc -Text "主要研究内容与实现成果总结"
    Delete-HeadingOnly -Document $doc -Text "创新点与应用价值总结"
    Delete-Section -Document $doc -StartText "系统不足与研究局限" -NextText "未来工作展望"
    Set-ParagraphText -Document $doc -OldText "未来工作展望" -NewText "展望" | Out-Null
    Delete-HeadingOnly -Document $doc -Text "智能能力与多模态协同的演进方向"
    Delete-HeadingOnly -Document $doc -Text "企业级平台化与治理能力的演进方向"
    Delete-HeadingOnly -Document $doc -Text "面向研究与应用结合的拓展方向"
    Delete-Section -Document $doc -StartText "本章小结" -NextText "参考文献" -StartOccurrence 7

    Trim-SectionText -Document $doc -HeadingText "研究内容和意义" -KeepParagraphCount 4
    Trim-SectionText -Document $doc -HeadingText "本文结构" -KeepParagraphCount 2
    Trim-SectionText -Document $doc -HeadingText "总结" -KeepParagraphCount 6
    Trim-SectionText -Document $doc -HeadingText "展望" -KeepParagraphCount 5

    Write-Output "[7/7] Rebuild manual TOC"
    Rebuild-ManualToc -Document $doc -Toc1Style $toc1Style -Toc2Style $toc2Style -Toc3Style $toc3Style

    $doc.Save()
    $doc.Close([ref]0)
    $word.Quit()
} catch {
    if ($doc) {
        try { $doc.Close([ref]0) } catch {}
    }
    if ($word) {
        try { $word.Quit() } catch {}
    }
    throw
}
