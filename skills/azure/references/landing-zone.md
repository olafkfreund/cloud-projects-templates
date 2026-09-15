# Azure landing zone (CAF Ready)

Verified 2026-09-15. Entry points: [CAF Ready](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/),
[What is an Azure landing zone?](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/),
[Design principles](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-principles).

## Why a landing zone

A landing zone is the pre-built environment (identity, management groups,
policy, networking, logging) that application teams deploy into. Build it once
so every application subscription inherits governance instead of re-inventing it.
CAF Ready is the phase where you prepare it before migrating or building workloads.

## Platform vs application landing zones

Source: [Platform vs application landing zones](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/#platform-landing-zone-vs-application-landing-zones).

| | Platform landing zone | Application landing zone |
| --- | --- | --- |
| Owned by | Central platform team | Workload team (or central, by agreement) |
| Contains | Identity, management, connectivity subscriptions; policies; hub network | One workload (or a related set) in its own subscription |
| Deployed with | ALZ accelerator / AVM ALZ modules | Subscription vending + workload IaC (this repo) |
| Changes | Rare, high-impact, reviewed by platform | Frequent, scoped to the workload |

Rule for this repo: workload code assumes an application landing zone exists.
Never create management groups, policy definitions at tenant root, or hub
networks from a workload repository.

## Conceptual architecture

Source: [Design areas and reference architecture](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-areas),
[Enterprise-scale architecture](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/enterprise-scale/).

Management group hierarchy ([Management groups](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org-management-groups),
[Management groups overview](https://learn.microsoft.com/en-us/azure/governance/management-groups/overview)):

```
Tenant Root Group
└── <org> (intermediate root; policies and RBAC start here, never at tenant root)
    ├── Platform
    │   ├── Identity        (domain controllers, Entra Connect)
    │   ├── Management      (Log Analytics, automation, monitoring)
    │   └── Connectivity    (hub VNet or Virtual WAN, DNS, firewall)
    ├── Landing zones
    │   ├── Corp            (internal, hub-connected workloads)
    │   └── Online          (internet-facing workloads)
    ├── Sandbox             (experiments, cheap, no hub connectivity)
    └── Decommissioned      (subscriptions on the way out)
```

Why: policy and RBAC inherit down the tree, so the hierarchy expresses
governance once. Keep it shallow (3 to 4 levels) and group by archetype, not by
department or environment ([Resource organization](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org)).

Subscriptions are the unit of scale, billing and isolation. One workload (or a
small set) per subscription; separate prod and non-prod subscriptions
([Subscriptions](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org-subscriptions)).

## The 8 design areas

Source: [Design areas](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-areas).

Environment design areas (decide first, hard to change):

1. [Azure billing and Entra tenant](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/azure-billing-microsoft-entra-tenant): one tenant, billing account structure, EA/MCA.
2. [Identity and access management](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access): Entra ID as the source of truth, RBAC via groups, PIM.
3. [Resource organization](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org): management groups, subscriptions, naming and tagging.
4. [Network topology and connectivity](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/network-topology-and-connectivity): hub-spoke or Virtual WAN, DNS, hybrid links.

Compliance design areas (iterate continuously):

5. [Security](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/security): Defender for Cloud, Key Vault, encryption, zero trust.
6. [Management](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/management): central Log Analytics, monitoring baseline, backup.
7. [Governance](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/governance): Azure Policy for audit and enforcement, cost governance.
8. [Platform automation and DevOps](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops): IaC, pipelines, subscription vending.

## Subscription vending

Source: [Subscription vending](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/subscription-vending),
[Subscription vending implementation](https://learn.microsoft.com/en-us/azure/architecture/landing-zones/subscription-vending).

Vending automates: create subscription, place it under the right management
group, apply tags and budget, create the spoke VNet and peer it to the hub,
assign RBAC to the workload group, create a deployment identity with a
federated credential. Terraform module: [Azure/lz-vending/azurerm](https://registry.terraform.io/modules/Azure/lz-vending/azurerm/latest).

Checklist for a vended application landing zone:

- [ ] Subscription sits under `Landing zones/Corp` or `Online`, not directly under root
- [ ] Budget and `cost-center`, `owner`, `environment` tags set at creation
- [ ] Spoke VNet address space allocated from the central IPAM, peered to the hub
- [ ] Workload team has `Contributor` (or narrower) on the subscription via a group
- [ ] Deployment identity is a user-assigned managed identity with a federated
      credential for the repo's CI; no client secret
- [ ] Diagnostic settings forward to the platform Log Analytics workspace
- [ ] Policy compliance is green before hand-over

## Network topology: hub-spoke vs Virtual WAN

Source: [Define a network topology](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology),
[Hub-spoke](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/hub-spoke-network-topology),
[Virtual WAN](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/virtual-wan-network-topology),
[Hub-spoke reference architecture](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/hybrid-networking/hub-spoke).

| | Customer-managed hub-spoke | Virtual WAN |
| --- | --- | --- |
| Hub | A VNet you build: firewall, gateway, DNS, Bastion | Microsoft-managed virtual hub |
| Routing | You write UDRs and peerings | Managed, any-to-any by default |
| Fits | Few regions, full control, existing NVA investment | Many regions/branches, large-scale SD-WAN/VPN, simpler ops |
| Cost | Cheaper at small scale | Fixed hub cost, cheaper operationally at scale |

Pick hub-spoke unless you have many regions or branches; both are supported by
the ALZ modules. Either way, spokes never hold shared services, and internet
egress goes through the hub firewall.

## Implementation: AVM and the ALZ Terraform modules

Source: [Implementation options](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/implementation-options),
[Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/),
[AVM on Microsoft Learn](https://learn.microsoft.com/en-us/community/content/azure-verified-modules),
[ALZ accelerator](https://azure.github.io/Azure-Landing-Zones/accelerator/),
[Landing zone Terraform deployment](https://learn.microsoft.com/en-us/azure/architecture/landing-zones/terraform/landing-zone-terraform),
[Landing zone Bicep deployment](https://learn.microsoft.com/en-us/azure/architecture/landing-zones/bicep/landing-zone-bicep).

Microsoft's recommended path is IaC with Azure Verified Modules, optionally
bootstrapped by the ALZ accelerator. AVM modules come in two kinds:
`avm-res-*` (one resource, e.g. a storage account) and `avm-ptn-*`
(a pattern composed of resources). All follow the [AVM Terraform spec](https://azure.github.io/Azure-Verified-Modules/specs/tf/)
and are listed in the [Terraform module index](https://azure.github.io/Azure-Verified-Modules/indexes/terraform/).

ALZ platform modules (used by the platform team, referenced here so you
recognise them):

| Module | Provides |
| --- | --- |
| [Azure/avm-ptn-alz/azurerm](https://registry.terraform.io/modules/Azure/avm-ptn-alz/azurerm/latest) | Management group hierarchy, policy definitions and assignments, RBAC |
| [Azure/avm-ptn-alz-management/azurerm](https://registry.terraform.io/modules/Azure/avm-ptn-alz-management/azurerm/latest) | Log Analytics, Automation, monitoring resources |
| [Azure/avm-ptn-alz-connectivity-hub-and-spoke-vnet/azurerm](https://registry.terraform.io/modules/Azure/avm-ptn-alz-connectivity-hub-and-spoke-vnet/azurerm/latest) | Hub-spoke connectivity |
| [Azure/avm-ptn-alz-connectivity-virtual-wan/azurerm](https://registry.terraform.io/modules/Azure/avm-ptn-alz-connectivity-virtual-wan/azurerm/latest) | Virtual WAN connectivity |
| [Azure/avm-ptn-network-hubnetworking/azurerm](https://registry.terraform.io/modules/Azure/avm-ptn-network-hubnetworking/azurerm/latest) | Hub VNet building block |
| [Azure/lz-vending/azurerm](https://registry.terraform.io/modules/Azure/lz-vending/azurerm/latest) | Subscription vending |

Workload-level AVM modules you will use directly are listed in
[terraform.md](terraform.md).

## Tailoring

You may add management groups or policies for your organisation, but keep the
ALZ archetypes and policy baseline intact so upstream updates still apply
([Tailor the ALZ architecture](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/tailoring-alz)).
