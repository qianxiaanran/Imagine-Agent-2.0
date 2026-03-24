param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
$wdStatisticPages = 2
$wdInformationPage = 3

function Get-ParagraphText {
    param([object]$Paragraph)
    $text = [string]$Paragraph.Range.Text
    $text = $text -replace [regex]::Escape([string][char]13), ""
    $text = $text -replace [regex]::Escape([string][char]7), ""
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
        [int]$Occurrence = 1
    )
    $count = 0
    foreach ($para in (Get-AllParagraphs -Document $Document)) {
        if ((Get-ParagraphText -Paragraph $para) -eq $Text) {
            $count++
            if ($count -eq $Occurrence) {
                return $para
            }
        }
    }
    return $null
}

function Get-StyleName {
    param([object]$Paragraph)
    try {
        return [string]$Paragraph.Range.Style.NameLocal
    } catch {
        try { return [string]$Paragraph.Style } catch { return "" }
    }
}

$word = $null
$doc = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open($Path, $false, $false)

    $tocTitle = Find-Paragraph -Document $doc -Text "目  录"
    $firstHeading = Find-Paragraph -Document $doc -Text "绪论"
    if (-not $tocTitle -or -not $firstHeading) {
        throw "TOC anchor not found."
    }

    $toc1Style = $doc.Styles.Item("TOC 1")
    $toc2Style = $doc.Styles.Item("TOC 2")
    $toc3Style = $doc.Styles.Item("TOC 3")

    $doc.Range($tocTitle.Range.End, $firstHeading.Range.Start).Delete()

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
        "业务流程分析",
        "智能对话与知识问答流程",
        "数据决策与内容生成流程",
        "智能审单与风险处理流程",
        "非功能需求分析",
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
        "特色业务模块设计",
        "文档检索与知识库模块设计",
        "决策分析与智能写作模块设计",
        "OCR与语音处理模块设计",
        "智能审单模块设计",
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

    $entries = @()
    foreach ($para in (Get-AllParagraphs -Document $doc)) {
        $text = Get-ParagraphText -Paragraph $para
        if (-not $text) { continue }
        if ($para.Range.Start -lt $firstHeading.Range.Start) { continue }
        $styleName = Get-StyleName -Paragraph $para
        if ($styleName -notin @("标题 1", "标题 2", "标题 3")) { continue }
        if (-not $selected.Contains($text)) { continue }

        $level = 3
        if ($styleName -eq "标题 1") { $level = 1 }
        elseif ($styleName -eq "标题 2") { $level = 2 }
        else { $level = 3 }

        $label = $text
        try {
            $listString = [string]$para.Range.ListFormat.ListString
        } catch {
            $listString = ""
        }
        if ($listString) {
            $label = "$listString $label"
        }
        $entries += [PSCustomObject]@{
            Paragraph = $para
            Label = $label
            Level = $level
        }
    }

    $placeholderLines = @()
    foreach ($entry in $entries) {
        $placeholderLines += "$($entry.Label)`t0"
    }
    $insertRange = Find-Paragraph -Document $doc -Text "绪论"
    $insertRange.Range.InsertBefore(([string]::Join([char]13, $placeholderLines)) + [char]13)

    $doc.Repaginate()

    $tocParagraphs = @()
    $firstHeading = Find-Paragraph -Document $doc -Text "绪论"
    foreach ($para in (Get-AllParagraphs -Document $doc)) {
        if ($para.Range.Start -le $tocTitle.Range.Start) { continue }
        if ($para.Range.Start -ge $firstHeading.Range.Start) { break }
        $text = Get-ParagraphText -Paragraph $para
        if (-not $text) { continue }
        $tocParagraphs += $para
    }

    for ($i = 0; $i -lt $entries.Count; $i++) {
        $page = [int]$entries[$i].Paragraph.Range.Information($wdInformationPage)
        $tocParagraphs[$i].Range.Text = "$($entries[$i].Label)`t$page" + [char]13
        try { $tocParagraphs[$i].Range.ListFormat.RemoveNumbers() | Out-Null } catch {}
        switch ($entries[$i].Level) {
            1 { $tocParagraphs[$i].Style = $toc1Style }
            2 { $tocParagraphs[$i].Style = $toc2Style }
            3 { $tocParagraphs[$i].Style = $toc3Style }
        }
    }

    $doc.Save()
    $doc.Close([ref]0)
    $word.Quit()
} catch {
    if ($doc) { try { $doc.Close([ref]0) } catch {} }
    if ($word) { try { $word.Quit() } catch {} }
    throw
}
